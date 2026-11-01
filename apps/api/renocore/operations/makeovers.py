"""Designs (material choices), redesign renders (G4) and their staleness."""

import hashlib
import re

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from renocore import vision
from renocore.database import session_scope
from renocore.operations import budgets as est
from renocore.operations import job_runner as jobs_svc
from renocore.operations import quotas as limits
from renocore.operations import workspaces as proj
from renocore.operations.failures import conflict, invalid, not_found
from renocore.operations.job_runner import JobCtx
from renocore.operations.materials_catalog import get_catalogue
from renocore.operations.photos import image_url, load_image, store_image
from renocore.operations.provider_factory import provider_for
from renocore.schemas.contracts import (
    AssignmentsPut,
    DesignCreate,
    DesignOut,
    DesignUpdate,
    RenderOut,
    RenderStarted,
)
from renocore.schemas.entities import OPENING_LABELS, QAResult
from renocore.settings import get_settings
from renocore.tables import (
    Design,
    DesignAssignment,
    ImageRow,
    Project,
    Render,
    Report,
    User,
    new_id,
)

log = structlog.get_logger("designs")
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def _parts_first() -> Exception:
    return conflict(
        "parts_not_confirmed", "Please confirm the parts of your house before choosing materials."
    )


# ---------------------------------------------------------------- serialisation


async def latest_render(session: AsyncSession, design_id: str) -> Render | None:
    return await session.scalar(
        select(Render)
        .where(Render.design_id == design_id)
        .order_by(Render.created_at.desc())
        .limit(1)
    )


def render_out(render: Render, stale: bool) -> RenderOut:
    return RenderOut(
        id=render.id,
        status=render.status,  # type: ignore[arg-type]
        image_url=image_url(render.image_id) if render.image_id else None,
        qa=QAResult.model_validate(render.qa) if render.qa else None,
        attempts=render.attempts,
        user_note=render.user_note,
        stale=stale,
        created_at=render.created_at,
    )


async def render_is_stale(
    session: AsyncSession, project: Project, design: Design, render: Render
) -> bool:
    return render.input_fingerprint != await est.render_fingerprint(session, project, design)


async def has_current_report(session: AsyncSession, project: Project) -> bool:
    """A design has a report built from its accepted, up-to-date look and finalised,
    up-to-date estimate (what the Cost & report step would offer for download)."""
    if project.stage != "designing":
        return False
    designs = await session.scalars(select(Design).where(Design.project_id == project.id))
    for design in designs:
        render = await latest_render(session, design.id)
        if render is None or render.status != "accepted":
            continue
        snap, stale = await est.estimate_state(session, project, design)
        if snap is None or stale or await render_is_stale(session, project, design, render):
            continue
        report = await session.scalar(
            select(Report.id)
            .where(
                Report.design_id == design.id,
                Report.estimate_version == snap.version,
                Report.render_id == render.id,
            )
            .limit(1)
        )
        if report is not None:
            return True
    return False


async def design_out(session: AsyncSession, project: Project, design: Design) -> DesignOut:
    render = await latest_render(session, design.id)
    render_dto = (
        render_out(render, await render_is_stale(session, project, design, render))
        if render
        else None
    )
    snap, stale = await est.estimate_state(session, project, design)
    return DesignOut(
        id=design.id,
        name=design.name,
        assignments=await est.assignments_of(session, design.id),
        render=render_dto,
        estimate_stale=stale,
        estimate_finalised=snap is not None,
        created_at=design.created_at,
    )


# ---------------------------------------------------------------- designs


async def list_designs(session: AsyncSession, project: Project) -> list[DesignOut]:
    designs = await session.scalars(
        select(Design).where(Design.project_id == project.id).order_by(Design.created_at, Design.id)
    )
    return [await design_out(session, project, d) for d in designs]


async def create_design(
    session: AsyncSession, user: User, project_id: str, body: DesignCreate
) -> DesignOut:
    project = await proj.get_project(session, user, project_id, for_update=True)
    if not project.regions_approved:
        raise _parts_first()
    source = None
    if body.copy_from is not None:
        source = await session.get(Design, body.copy_from)
        if source is None or source.project_id != project.id:
            raise not_found("design")
    design = Design(project_id=project.id, name=body.name.strip() or body.name)
    session.add(design)
    await session.flush()
    if source is not None:
        for a in await est.assignments_of(session, source.id):
            session.add(
                DesignAssignment(
                    design_id=design.id,
                    region_id=a.region_id,
                    material_id=a.material_id,
                    color=a.color,
                )
            )
    proj.touch(project)
    await session.commit()
    return await design_out(session, project, design)


async def put_assignments(
    session: AsyncSession, user: User, design_id: str, body: AssignmentsPut
) -> DesignOut:
    design, project = await proj.get_design(session, user, design_id, for_update=True)
    if not project.regions_approved:
        raise _parts_first()
    regions = {r.id: r for r in await proj.approved_regions(session, project)}
    catalogue = get_catalogue()
    seen: set[str] = set()
    for a in body.assignments:
        region = regions.get(a.region_id)
        if region is None:
            raise invalid("unknown_part", "One of these parts no longer exists. Please reload.")
        if a.region_id in seen:
            raise invalid("duplicate_part", "Each part can only have one material.")
        seen.add(a.region_id)
        if region.label in OPENING_LABELS:
            raise invalid("opening", "Windows and doors are kept as they are.")
        material = catalogue.get(a.material_id)
        if material is None:
            raise invalid("unknown_material", "We don't know that material. Please pick another.")
        if region.label not in material.applicable_labels:
            raise invalid(
                "material_not_applicable",
                f"{material.name} can't be used on this part of the house.",
            )
        if a.color is not None and not _HEX.match(a.color):
            raise invalid("invalid_color", "Please pick a colour from the list.")
    existing = {
        a.region_id: a
        for a in await session.scalars(
            select(DesignAssignment).where(DesignAssignment.design_id == design.id)
        )
    }
    for region_id, row in existing.items():
        if region_id not in seen:
            await session.delete(row)
    for a in body.assignments:
        row = existing.get(a.region_id)
        if row is None:
            session.add(
                DesignAssignment(
                    design_id=design.id,
                    region_id=a.region_id,
                    material_id=a.material_id,
                    color=a.color,
                )
            )
        else:
            row.material_id = a.material_id
            row.color = a.color
    proj.touch(project)
    await session.commit()
    return await design_out(session, project, design)


async def update_design(
    session: AsyncSession, user: User, design_id: str, body: DesignUpdate
) -> DesignOut:
    design, project = await proj.get_design(session, user, design_id, for_update=True)
    design.name = body.name.strip() or body.name
    proj.touch(project)
    await session.commit()
    return await design_out(session, project, design)


async def delete_design(session: AsyncSession, user: User, design_id: str) -> None:
    design, project = await proj.get_design(session, user, design_id, for_update=True)
    await session.delete(design)
    proj.touch(project)
    await session.commit()


# ---------------------------------------------------------------- renders (G4)


async def start_render(
    session: AsyncSession, user: User, design_id: str, note: str | None
) -> RenderStarted:
    design, project = await proj.get_design(session, user, design_id, for_update=True)
    if not project.regions_approved:
        raise _parts_first()
    if not await est.assignments_of(session, design.id):
        raise conflict("no_materials", "Choose a material for at least one part first.")
    note = (note or "").strip() or None
    fp = await est.render_fingerprint(session, project, design)
    note_hash = hashlib.sha256((note or "").encode()).hexdigest()[:16]
    idem_key = f"render:{design.id}:{fp[:32]}:{note_hash}"
    active = await jobs_svc.find_active(session, idem_key)
    if active is not None:
        render = await session.scalar(select(Render).where(Render.job_id == active.id))
        if render is not None:
            await session.commit()
            return RenderStarted(render=render_out(render, False), job_id=active.id)
    await limits.check_new_look_limit(session, user)
    run_id = new_id()  # committed together with the render so a second click finds both
    render = Render(
        design_id=design.id,
        status="queued",
        input_fingerprint=fp,
        user_note=note,
        job_id=run_id,
    )
    session.add(render)
    await session.flush()
    run, _ = await jobs_svc.enqueue(
        session,
        project_id=project.id,
        design_id=design.id,
        kind="render",
        idem_key=idem_key,
        payload={"render_id": render.id},
        run_id=run_id,
    )
    return RenderStarted(render=render_out(render, False), job_id=run.id)


async def get_render(session: AsyncSession, user: User, design_id: str) -> RenderOut | None:
    design, project = await proj.get_design(session, user, design_id)
    render = await latest_render(session, design.id)
    if render is None:
        return None
    return render_out(render, await render_is_stale(session, project, design, render))


async def accept_render(session: AsyncSession, user: User, render_id: str) -> RenderOut:
    render, design = await proj.get_render(session, user, render_id)
    project = await jobs_svc.lock_project(session, design.project_id)
    latest = await latest_render(session, design.id)
    if latest is None or latest.id != render.id:
        raise conflict(
            "not_latest", "A newer picture of this design exists. Please review that one."
        )
    if render.status not in ("ready", "accepted"):
        raise conflict("render_not_ready", "Your new look isn't ready yet.")
    if await render_is_stale(session, project, design, render):
        raise conflict(
            "design_changed",
            "This design changed after the picture was made. Please create a new look first.",
        )
    await session.execute(
        update(Render)
        .where(Render.design_id == design.id, Render.id != render.id, Render.status == "accepted")
        .values(status="ready", accepted=False)
    )
    render.status = "accepted"
    render.accepted = True
    proj.touch(project)
    await session.commit()
    return render_out(render, False)


async def run_render(ctx: JobCtx) -> None:
    settings = get_settings()
    render_id = ctx.payload["render_id"]
    async with session_scope() as session:
        render = await session.get(Render, render_id)
        if render is None:
            return
        design = await session.get(Design, render.design_id)
        project = await session.get(Project, ctx.project_id)
        if design is None or project is None or not project.working_image_id:
            return
        working = await session.get(ImageRow, project.working_image_id)
        regions = await proj.approved_regions(session, project)
        assignments = await est.assignments_of(session, design.id)
        render.status = "running"
        await session.commit()
        note = render.user_note
    assert working is not None
    photo = await load_image(working)
    outcome = await vision.render_design(
        provider_for(ctx.project_id, ctx.run_id),
        photo,
        regions,
        assignments,
        get_catalogue(),
        note,
        settings.render_max_auto_regenerate,
        settings.render_qa_threshold,
        cache_salt=render_id,  # every render / redo is a fresh generation
    )
    async with session_scope() as session:
        render = await session.get(Render, render_id)
        if render is None:
            return
        image = await store_image(session, ctx.project_id, "render", outcome.image, "JPEG")
        zone = await store_image(session, ctx.project_id, "zone_map", outcome.zone_map, "PNG")
        render.image_id = image.id
        render.zone_map_image_id = zone.id
        render.qa = outcome.qa.model_dump(mode="json")
        render.attempts = outcome.attempts
        render.status = "ready"
        render.error = None
        await session.commit()
    log.info(
        "render_done", render_id=render_id, attempts=outcome.attempts, passed=outcome.qa.passed
    )


async def render_failed(ctx: JobCtx) -> None:
    async with session_scope() as session:
        render = await session.get(Render, ctx.payload.get("render_id"))
        if render is not None:
            render.status = "failed"
            render.error = jobs_svc.FAILURE_MESSAGE["render"]
            await session.commit()
