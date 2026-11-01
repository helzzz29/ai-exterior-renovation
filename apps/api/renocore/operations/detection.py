"""Background handlers: photo analysis (C1 || C2 -> C3) and material suggestions (C4)."""

import asyncio

import structlog
from sqlalchemy import select, update

from renocore import pixels, vision
from renocore.database import session_scope
from renocore.operations import workspaces as proj
from renocore.operations.image_pipeline import run_image_work
from renocore.operations.job_runner import JobCtx
from renocore.operations.lifecycle import region_fingerprint
from renocore.operations.materials_catalog import get_catalogue
from renocore.operations.photos import load_image, store_image
from renocore.operations.provider_factory import provider_for
from renocore.schemas.entities import LABELS, MaterialAdvice, PhotoCheckResult, Region
from renocore.settings import get_settings
from renocore.tables import ImageRow, MaterialAdviceRow, Project, RegionRow, new_id

log = structlog.get_logger("jobs.analysis")

STEP_CHECKING = "Checking your photo"
STEP_FINDING = "Finding walls, windows and balconies"
STEP_MEASURING = "Measuring"


async def _current_photo(project_id: str, image_id: str) -> ImageRow | None:
    async with session_scope() as session:
        project = await session.get(Project, project_id)
        if project is None or project.working_image_id != image_id:
            return None  # superseded by a newer upload (or project deleted)
        return await session.get(ImageRow, image_id)


async def run_analysis(ctx: JobCtx) -> None:
    settings = get_settings()
    image_id = ctx.payload["working_image_id"]
    working = await _current_photo(ctx.project_id, image_id)
    if working is None:
        log.info("analysis_superseded", image_id=image_id)
        return
    photo = await load_image(working)
    provider = provider_for(ctx.project_id, ctx.run_id)

    await ctx.set_step(STEP_CHECKING)
    # speculative: segmentation starts before the photo verdict is known
    answers, candidates = await asyncio.gather(provider.whole_photo(photo), provider.segment(photo))

    await ctx.set_step(STEP_FINDING)
    regions = [
        Region(
            id=new_id(),
            label=c.label_hint if c.label_hint in LABELS else "wall",  # type: ignore[arg-type]
            polygon=c.polygon,
            source="gemini",
        )
        for c in candidates
    ]
    labels = await provider.label_regions(photo, regions) if regions else {}
    labelled = vision.apply_labels(regions, labels, settings.region_confidence_threshold)
    proposals = [  # our own ids (stable UUID strings) for the suggested boxes
        p.model_copy(update={"id": new_id(), "proposed": True})
        for p in vision.proposed_regions(answers, labelled, photo.width, photo.height)
    ]

    await ctx.set_step(STEP_MEASURING)
    async with session_scope() as session:
        project = await session.get(Project, ctx.project_id, with_for_update=True)
        if project is None or project.working_image_id != image_id:
            return
        checks = PhotoCheckResult.model_validate(project.photo_checks)
        verdict = vision.photo_verdict(checks, answers)
        project.whole_photo = answers.model_dump(mode="json")
        project.verdict = verdict.model_dump(mode="json")
        # a retried job must not duplicate parts
        await session.execute(
            update(RegionRow)
            .where(RegionRow.project_id == project.id, RegionRow.active.is_(True))
            .values(active=False)
        )
        if verdict.status == "reject":
            project.stage = "photo_rejected"  # detected parts are discarded
        else:
            for position, region in enumerate([*labelled, *proposals]):
                crop_id = None
                if region.needs_check:  # close-up for the "Is this a pillar?" card
                    crop = await run_image_work(pixels.region_crop, photo, region.polygon)
                    crop_id = (await store_image(session, project.id, "crop", crop)).id
                session.add(
                    RegionRow(
                        id=region.id,
                        project_id=project.id,
                        image_id=image_id,
                        label=region.label,
                        polygon=[[float(x), float(y)] for x, y in region.polygon],
                        source=region.source,
                        label_confidence=region.label_confidence,
                        needs_check=region.needs_check,
                        checked=region.checked,
                        proposed=region.proposed,
                        position=position,
                        crop_image_id=crop_id,
                    )
                )
            project.stage = "photo_warning" if verdict.status == "warn" else "regions_review"
        proj.touch(project)
        await session.commit()
    log.info(
        "analysis_done", verdict=verdict.status, regions=len(labelled), proposed=len(proposals)
    )


async def analysis_failed(ctx: JobCtx) -> None:
    """After the last retry: let the user upload again."""
    async with session_scope() as session:
        project = await session.get(Project, ctx.project_id, with_for_update=True)
        if project is not None and project.working_image_id == ctx.payload.get("working_image_id"):
            if project.stage == "analyzing":
                project.stage = "upload"
                await session.commit()


async def run_material_advice(ctx: JobCtx) -> None:
    region_ids: list[str] = ctx.payload["region_ids"]
    async with session_scope() as session:
        project = await session.get(Project, ctx.project_id)
        if project is None or not project.working_image_id:
            return
        working = await session.get(ImageRow, project.working_image_id)
        rows = list(
            await session.scalars(
                select(RegionRow).where(RegionRow.id.in_(region_ids), RegionRow.active.is_(True))
            )
        )
    if not rows or working is None:
        return
    photo = await load_image(working)
    provider = provider_for(ctx.project_id, ctx.run_id)
    advice: list[MaterialAdvice] = await provider.material_advice(
        photo, [proj.to_region(r) for r in rows], get_catalogue()
    )
    fingerprints = {r.id: region_fingerprint(r) for r in rows}
    async with session_scope() as session:
        current = {
            r.id: r
            for r in await session.scalars(
                select(RegionRow).where(RegionRow.id.in_(region_ids), RegionRow.active.is_(True))
            )
        }
        existing = {
            a.region_id: a
            for a in await session.scalars(
                select(MaterialAdviceRow).where(MaterialAdviceRow.region_id.in_(region_ids))
            )
        }
        for item in advice:
            row = current.get(item.region_id)
            # skip parts that were removed or edited while suggestions were being prepared
            if row is None or region_fingerprint(row) != fingerprints.get(item.region_id):
                continue
            if item.region_id in existing:
                await session.delete(existing[item.region_id])
                await session.flush()
            session.add(
                MaterialAdviceRow(
                    project_id=ctx.project_id,
                    region_id=item.region_id,
                    region_fingerprint=fingerprints[item.region_id],
                    payload=item.model_dump(mode="json"),
                )
            )
        await session.commit()
