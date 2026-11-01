"""Project workflow: photo (S1, G1), parts of the house (G2) and size check (G3).

Stages (ProjectStage): upload -> analyzing -> photo_rejected | photo_warning | regions_review
-> scale_review -> designing.
"""

import hashlib

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from renocore import pixels
from renocore.operations import budgets as est
from renocore.operations import job_runner as jobs_svc
from renocore.operations import quotas as limits
from renocore.operations import workspaces as proj
from renocore.operations.failures import conflict, invalid
from renocore.operations.image_pipeline import run_image_work
from renocore.operations.materials_catalog import get_catalogue
from renocore.operations.photos import encode, sniff, store_bytes
from renocore.operations.signatures import fingerprint
from renocore.schemas.contracts import (
    PhotoUploadResult,
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
    RegionsOut,
    RegionsPut,
    ScaleConfirm,
    ScaleOut,
)
from renocore.schemas.entities import OPENING_LABELS, Confidence, Measurements, ScaleResult
from renocore.settings import get_settings
from renocore.tables import (
    Design,
    DesignAssignment,
    MaterialAdviceRow,
    Project,
    RegionRow,
    User,
)

POST_PHOTO_STAGES = ("regions_review", "scale_review", "designing")
DEFAULT_DESIGN_NAME = "Design 1"

# ---------------------------------------------------------------- projects


async def create_project(session: AsyncSession, user: User, body: ProjectCreate) -> ProjectOut:
    project = Project(
        owner_id=user.id,
        name=body.name.strip() or body.name,
        stage="upload",
        measurements=body.measurements.model_dump(mode="json"),
        extras={},
    )
    session.add(project)
    await session.commit()
    return await proj.project_out(session, project)


async def list_projects(session: AsyncSession, user: User) -> list[Project]:
    rows = await session.scalars(
        select(Project).where(Project.owner_id == user.id).order_by(Project.updated_at.desc())
    )
    return list(rows)


async def update_project(
    session: AsyncSession, user: User, project_id: str, body: ProjectUpdate
) -> ProjectOut:
    project = await proj.get_project(session, user, project_id, for_update=True)
    if body.name is not None:
        project.name = body.name
    if body.measurements is not None:
        new = body.measurements.model_dump(mode="json")
        if new != (project.measurements or {}):
            project.measurements = new
            if project.regions_approved:  # "Size reference" row of the change table
                await _rescale_after_change(session, project)
    proj.touch(project)
    await session.commit()
    return await proj.project_out(session, project)


async def delete_project(session: AsyncSession, user: User, project_id: str) -> None:
    project = await proj.get_project(session, user, project_id)
    await session.delete(project)
    await session.commit()


# ---------------------------------------------------------------- photo (S1, G1)


async def _reset_for_new_photo(session: AsyncSession, project: Project) -> None:
    """New photo: old parts go, designs keep their names but lose their choices, and every
    render/estimate becomes stale through its fingerprint (nothing is deleted)."""
    await session.execute(
        update(RegionRow)
        .where(RegionRow.project_id == project.id, RegionRow.active.is_(True))
        .values(active=False)
    )
    design_ids = select(Design.id).where(Design.project_id == project.id)
    await session.execute(
        delete(DesignAssignment).where(DesignAssignment.design_id.in_(design_ids))
    )
    await session.execute(
        delete(MaterialAdviceRow).where(MaterialAdviceRow.project_id == project.id)
    )
    project.regions_approved = False
    project.scale = None
    project.scale_confirmed = False
    project.verdict = None
    project.verdict_overridden = False
    project.whole_photo = None


async def upload_photo(
    session: AsyncSession, user: User, project_id: str, data: bytes
) -> PhotoUploadResult:
    settings = get_settings()
    project = await proj.get_project(session, user, project_id)
    if not data:
        raise invalid("empty_file", "The file is empty. Please choose a photo of your house.")
    if len(data) > settings.max_upload_bytes:
        mb = settings.max_upload_bytes // (1024 * 1024)
        raise invalid("too_large", f"This photo is too large. Please upload one under {mb} MB.")

    try:
        original = await run_image_work(pixels.load_upload, data)
    except pixels.ImageRejected as exc:
        raise invalid(exc.code, exc.message) from exc
    working = await run_image_work(pixels.make_working_copy, original)
    checks = await run_image_work(pixels.check_photo, working)
    hard = [i for i in checks.issues if i.severity == "hard"]
    if hard:  # instant, specific message; nothing stored or enqueued
        raise invalid(hard[0].code, hard[0].message)

    project = await jobs_svc.lock_project(session, project.id)
    idem_key = f"analyze:{project.id}:{hashlib.sha256(data).hexdigest()}"
    existing = await jobs_svc.find_active(session, idem_key)
    if existing is not None:  # same photo submitted twice while it is being analysed
        await session.commit()
        return PhotoUploadResult(
            project=await proj.project_out(session, project), job_id=existing.id
        )
    await limits.check_photo_limit(session, user)

    ext, content_type = sniff(data)
    if content_type == "application/octet-stream":  # decodable but unusual; keep a JPEG copy
        data_to_store = await run_image_work(encode, original, "JPEG")
        ext, content_type = "jpg", "image/jpeg"
    else:
        data_to_store = data
    original_row = await store_bytes(
        session,
        project.id,
        "original",
        data_to_store,
        original.width,
        original.height,
        content_type,
        ext,
    )
    working_bytes = await run_image_work(encode, working, "JPEG")
    working_row = await store_bytes(
        session,
        project.id,
        "working",
        working_bytes,
        working.width,
        working.height,
        "image/jpeg",
        "jpg",
    )
    await _reset_for_new_photo(session, project)
    project.original_image_id = original_row.id
    project.working_image_id = working_row.id
    project.photo_checks = checks.model_dump(mode="json")
    project.stage = "analyzing"
    proj.touch(project)
    run, _ = await jobs_svc.enqueue(
        session,
        project_id=project.id,
        kind="analyze_photo",
        idem_key=idem_key,
        payload={"working_image_id": working_row.id},
    )
    return PhotoUploadResult(project=await proj.project_out(session, project), job_id=run.id)


async def continue_with_warning(session: AsyncSession, user: User, project_id: str) -> ProjectOut:
    project = await proj.get_project(session, user, project_id, for_update=True)
    if project.stage != "photo_warning":
        raise conflict("no_photo_warning", "There is no photo warning to continue past.")
    project.verdict_overridden = True
    project.stage = "regions_review"
    proj.touch(project)
    await session.commit()
    return await proj.project_out(session, project)


# ---------------------------------------------------------------- parts of the house (G2)


async def get_regions(session: AsyncSession, project: Project) -> RegionsOut:
    rows = await proj.active_region_rows(session, project.id)
    return RegionsOut(
        regions=[proj.region_out(r) for r in rows],
        approved=project.regions_approved,
        pending_checks=proj.pending_checks(rows),
    )


def _norm_polygon(points: list, width: int | None, height: int | None) -> list[list[float]]:
    out = []
    for x, y in points:
        x, y = float(x), float(y)
        if width is not None and height is not None:
            x = min(max(x, 0.0), float(width))
            y = min(max(y, 0.0), float(height))
        out.append([round(x, 2), round(y, 2)])
    return out


def _area(points: list[list[float]]) -> float:
    s = 0.0
    for i, (x1, y1) in enumerate(points):
        x2, y2 = points[(i + 1) % len(points)]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2


def region_fingerprint(row: RegionRow) -> str:
    return fingerprint(row.label, row.polygon)


def _material_fits(material_id: str, label: str) -> bool:
    material = get_catalogue().get(material_id)
    return material is not None and label in material.applicable_labels


async def put_regions(
    session: AsyncSession, user: User, project_id: str, body: RegionsPut
) -> RegionsOut:
    project = await proj.get_project(session, user, project_id, for_update=True)
    if project.stage not in POST_PHOTO_STAGES:
        raise conflict(
            "photo_not_ready", "Your photo needs to be checked before you can edit its parts."
        )
    working = None
    if project.working_image_id:
        from renocore.tables import ImageRow

        working = await session.get(ImageRow, project.working_image_id)
    width = working.width if working else None
    height = working.height if working else None

    rows = await proj.active_region_rows(session, project.id)
    by_id = {r.id: r for r in rows}
    seen: set[str] = set()
    for item in body.regions:
        if item.id is not None:
            if item.id not in by_id:
                raise invalid("unknown_part", "One of these parts no longer exists. Please reload.")
            if item.id in seen:
                raise invalid("duplicate_part", "The same part was sent twice.")
            seen.add(item.id)

    changed = False
    removed_ids: list[str] = []
    relabelled: dict[str, str] = {}
    for position, item in enumerate(body.regions):
        polygon = _norm_polygon(list(item.polygon), width, height)
        if _area(polygon) < 1.0:
            raise invalid("invalid_shape", "One of the outlines is too small. Please redraw it.")
        if item.id is None:  # drawn by the user: their label is final
            session.add(
                RegionRow(
                    project_id=project.id,
                    image_id=project.working_image_id,
                    label=item.label,
                    polygon=polygon,
                    source="user",
                    label_confidence=None,
                    needs_check=False,
                    checked=True,
                    proposed=False,
                    position=position,
                )
            )
            changed = True
            continue
        row = by_id[item.id]
        row.position = position
        polygon_changed = polygon != _norm_polygon(row.polygon, None, None)
        label_changed = item.label != row.label
        if polygon_changed or label_changed:
            row.source = "user"
            row.version += 1
            changed = True
            if polygon_changed:
                row.polygon = polygon
                row.crop_image_id = None
            if label_changed:
                relabelled[row.id] = item.label
                row.label = item.label
                row.label_confidence = None
                row.checked = True  # the user's choice is final; no relabel job needed
        if item.checked != row.checked and not label_changed:
            row.checked = item.checked
        if row.proposed and not item.proposed:  # "Yes, keep it"
            row.proposed = False
            changed = True
    for row in rows:
        if row.id not in seen:
            row.active = False
            removed_ids.append(row.id)
            changed = True

    if removed_ids:
        await session.execute(
            delete(DesignAssignment).where(DesignAssignment.region_id.in_(removed_ids))
        )
        await session.execute(
            delete(MaterialAdviceRow).where(MaterialAdviceRow.region_id.in_(removed_ids))
        )
    if relabelled:  # drop choices that no longer fit the new kind of part
        assigned = await session.scalars(
            select(DesignAssignment).where(DesignAssignment.region_id.in_(list(relabelled)))
        )
        for a in assigned:
            label = relabelled[a.region_id]
            if label in OPENING_LABELS or not _material_fits(a.material_id, label):
                await session.delete(a)

    if changed and project.regions_approved:  # G2 reopens; dependants become stale
        project.regions_approved = False
        project.stage = "regions_review"
    if changed:
        proj.touch(project)
    await session.commit()
    return await get_regions(session, project)


async def ensure_default_design(session: AsyncSession, project: Project) -> None:
    # lock the project row so concurrent requests cannot both create the default design
    await session.execute(select(Project.id).where(Project.id == project.id).with_for_update())
    exists = await session.scalar(select(Design.id).where(Design.project_id == project.id).limit(1))
    if exists is None:
        session.add(Design(project_id=project.id, name=DEFAULT_DESIGN_NAME))


def _keep_confirmation(previous: ScaleResult | None, new: ScaleResult, was_confirmed: bool) -> bool:
    if new.confidence == Confidence.high and not new.needs_measurement:
        return True  # a real measurement needs no extra confirmation
    if not was_confirmed or previous is None or new.needs_measurement:
        return False
    return (
        new.method == previous.method
        and abs(new.ft_per_px - previous.ft_per_px) <= 0.01 * previous.ft_per_px
    )


async def _rescale_after_change(session: AsyncSession, project: Project) -> None:
    previous = proj.scale_of(project)
    new = await est.recompute_scale(session, project)
    project.scale_confirmed = _keep_confirmation(previous, new, project.scale_confirmed)
    if project.stage in ("scale_review", "designing"):
        project.stage = "designing" if project.scale_confirmed else "scale_review"
        if project.stage == "designing":
            await ensure_default_design(session, project)


async def approve_regions(session: AsyncSession, user: User, project_id: str) -> ProjectOut:
    project = await proj.get_project(session, user, project_id, for_update=True)
    if project.regions_approved and project.stage in ("scale_review", "designing"):
        await session.commit()
        return await proj.project_out(session, project)  # already approved: no-op
    if project.stage != "regions_review":
        raise conflict(
            "photo_not_ready", "Your photo needs to be checked before you can confirm its parts."
        )
    rows = await proj.active_region_rows(session, project.id)
    pending = proj.pending_checks(rows)
    if pending:
        noun = "part" if pending == 1 else "parts"
        raise conflict(
            "checks_pending",
            f"Please check the {pending} {noun} marked “Please check” before continuing.",
        )
    accepted = [r for r in rows if not r.proposed]
    if not any(r.label not in OPENING_LABELS for r in accepted):
        raise conflict("no_parts", "Please mark at least one wall or other part of your house.")

    project.regions_approved = True
    project.regions_version += 1
    previous = proj.scale_of(project)
    new_scale = await est.recompute_scale(session, project)
    project.scale_confirmed = _keep_confirmation(previous, new_scale, project.scale_confirmed)
    project.stage = "designing" if project.scale_confirmed else "scale_review"
    if project.stage == "designing":
        await ensure_default_design(session, project)
    proj.touch(project)

    # material suggestions only for parts that are new or changed since the last approval
    advice_rows = await session.scalars(
        select(MaterialAdviceRow).where(MaterialAdviceRow.project_id == project.id)
    )
    current = {a.region_id: a.region_fingerprint for a in advice_rows}
    needed = [
        r.id
        for r in accepted
        if r.label not in OPENING_LABELS and current.get(r.id) != region_fingerprint(r)
    ]
    if needed:
        await session.execute(
            delete(MaterialAdviceRow).where(MaterialAdviceRow.region_id.in_(needed))
        )
        await jobs_svc.enqueue(
            session,
            project_id=project.id,
            kind="material_advice",
            idem_key=f"advice:{project.id}:{project.regions_version}",
            payload={"region_ids": needed},
        )
    else:
        await session.commit()
    return await proj.project_out(session, project)


# ---------------------------------------------------------------- size check (G3)


def scale_out(project: Project) -> ScaleOut:
    scale = proj.scale_of(project)
    if scale is None:
        raise conflict(
            "parts_not_confirmed", "Please confirm the parts of your house before the size check."
        )
    return ScaleOut(
        ft_per_px=scale.ft_per_px,
        method=scale.method,
        confidence=scale.confidence,
        facade_width_ft=scale.facade_width_ft,
        reference_box=scale.reference_box_px,
        explanation=scale.explanation,
        needs_measurement=scale.needs_measurement,
        confirmed=project.scale_confirmed,
    )


async def confirm_scale(
    session: AsyncSession, user: User, project_id: str, body: ScaleConfirm
) -> ScaleOut:
    project = await proj.get_project(session, user, project_id, for_update=True)
    if not project.regions_approved or project.scale is None:
        raise conflict(
            "parts_not_confirmed", "Please confirm the parts of your house before the size check."
        )
    has_measurement = any(
        v is not None for v in (body.facade_width_ft, body.facade_height_ft, body.reference_line)
    )
    if has_measurement:
        m = proj.measurements(project)
        data = m.model_dump()
        if body.facade_width_ft is not None:
            data["facade_width_ft"] = body.facade_width_ft
        if body.facade_height_ft is not None:
            data["facade_height_ft"] = body.facade_height_ft
        if body.reference_line is not None:
            data["reference_line"] = body.reference_line
        project.measurements = Measurements.model_validate(data).model_dump(mode="json")
        scale = await est.recompute_scale(session, project)
        if scale.needs_measurement:
            raise invalid(
                "measurement_unusable",
                "We couldn't use that measurement. Please check the number and try again.",
            )
    elif body.accept:
        scale = proj.scale_of(project)
        assert scale is not None
        if scale.needs_measurement:
            raise conflict(
                "measurement_needed",
                "We need one measurement to calculate costs accurately. Enter the width of "
                "your house, or draw a line on any wall and tell us how long it is.",
            )
    else:
        raise invalid("nothing_to_confirm", "Please confirm the size or enter one measurement.")
    project.scale_confirmed = True
    if project.stage == "scale_review":
        project.stage = "designing"
    if project.stage == "designing":
        await ensure_default_design(session, project)
    proj.touch(project)
    await session.commit()
    return scale_out(project)
