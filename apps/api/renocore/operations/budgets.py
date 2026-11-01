"""Scale, live estimates, finalised snapshots, rates and the staleness fingerprints."""

import re

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from renocore import costing, pixels
from renocore.operations import workspaces as proj
from renocore.operations.failures import conflict, invalid
from renocore.operations.materials_catalog import get_catalogue
from renocore.operations.signatures import fingerprint
from renocore.schemas.contracts import EstimateOut, RatesOut, RatesPut
from renocore.schemas.entities import (
    Assignment,
    BoxFraction,
    EstimateInputs,
    Extras,
    RateOverride,
    Region,
    ScaleInputs,
    ScaleResult,
    WholePhotoAnswers,
)
from renocore.tables import (
    Design,
    DesignAssignment,
    EstimateSnapshot,
    ImageRow,
    Project,
    RateOverrideRow,
    RegionRow,
)

# ---------------------------------------------------------------- scale


def floors_from_answer(answers: WholePhotoAnswers | None) -> int | None:
    if answers is None:
        return None
    match = re.match(r"\s*(\d+)", answers.floors.choice)
    return int(match.group(1)) if match else None


def whole_photo(project: Project) -> WholePhotoAnswers | None:
    return WholePhotoAnswers.model_validate(project.whole_photo) if project.whole_photo else None


async def scale_inputs(
    session: AsyncSession, project: Project, regions: list[Region]
) -> ScaleInputs:
    answers = whole_photo(project)
    door_box_px = None
    if answers is not None and answers.main_door is not None and project.working_image_id:
        working = await session.get(ImageRow, project.working_image_id)
        if working is not None:
            door_box_px = pixels.fraction_box_to_px(
                BoxFraction.model_validate(answers.main_door.box), working.width, working.height
            )
    return ScaleInputs(
        regions=regions,
        measurements=proj.measurements(project),
        door_visible=answers.door_visible if answers else None,
        door_box_px=door_box_px,
        floors_answer=floors_from_answer(answers),
        photo_warned=project.verdict_overridden,
    )


async def recompute_scale(session: AsyncSession, project: Project) -> ScaleResult:
    regions = await proj.approved_regions(session, project)
    result = costing.resolve_scale(await scale_inputs(session, project, regions))
    project.scale = result.model_dump(mode="json")
    return result


def floors_for(project: Project) -> int:
    m = proj.measurements(project)
    return m.floors or floors_from_answer(whole_photo(project)) or 1


# ---------------------------------------------------------------- rates


def extras_of(project: Project) -> Extras:
    return Extras.model_validate(project.extras or {})


async def overrides_of(session: AsyncSession, project_id: str) -> list[RateOverride]:
    rows = await session.scalars(
        select(RateOverrideRow)
        .where(RateOverrideRow.project_id == project_id)
        .order_by(RateOverrideRow.material_id)
    )
    return [
        RateOverride(
            material_id=r.material_id, material_rate=r.material_rate, labour_rate=r.labour_rate
        )
        for r in rows
    ]


async def get_rates(session: AsyncSession, project: Project) -> RatesOut:
    return RatesOut(overrides=await overrides_of(session, project.id), extras=extras_of(project))


async def put_rates(session: AsyncSession, project: Project, body: RatesPut) -> RatesOut:
    catalogue = get_catalogue()
    seen: set[str] = set()
    for o in body.overrides:
        if o.material_id not in catalogue:
            raise invalid("unknown_material", "One of the prices is for a material we don't know.")
        if o.material_id in seen:
            raise invalid("duplicate_rate", "Each material can only have one price change.")
        seen.add(o.material_id)
    await session.execute(delete(RateOverrideRow).where(RateOverrideRow.project_id == project.id))
    for o in body.overrides:
        if o.material_rate is None and o.labour_rate is None:
            continue
        session.add(
            RateOverrideRow(
                project_id=project.id,
                material_id=o.material_id,
                material_rate=o.material_rate,
                labour_rate=o.labour_rate,
            )
        )
    project.extras = body.extras.model_dump(mode="json")
    proj.touch(project)
    await session.commit()
    return await get_rates(session, project)


# ---------------------------------------------------------------- assignments & inputs


async def assignments_of(session: AsyncSession, design_id: str) -> list[Assignment]:
    rows = await session.execute(
        select(DesignAssignment)
        .join(RegionRow, RegionRow.id == DesignAssignment.region_id)
        .where(DesignAssignment.design_id == design_id, RegionRow.active.is_(True))
        .order_by(DesignAssignment.region_id)
    )
    return [
        Assignment(region_id=a.region_id, material_id=a.material_id, color=a.color)
        for a in rows.scalars()
    ]


async def estimate_inputs(
    session: AsyncSession, project: Project, design: Design
) -> EstimateInputs | None:
    """None when the inputs aren't settled yet (parts not approved / no size reference)."""
    scale = proj.scale_of(project)
    if not project.regions_approved or scale is None:
        return None
    return EstimateInputs(
        regions=await proj.approved_regions(session, project),
        scale=scale,
        assignments=await assignments_of(session, design.id),
        materials=get_catalogue(),
        overrides=await overrides_of(session, project.id),
        extras=extras_of(project),
        floors=floors_for(project),
        scale_confirmed=project.scale_confirmed,
    )


def inputs_fingerprint(inputs: EstimateInputs) -> str:
    return fingerprint("estimate-v1", inputs)


async def latest_snapshot(session: AsyncSession, design_id: str) -> EstimateSnapshot | None:
    return await session.scalar(
        select(EstimateSnapshot)
        .where(EstimateSnapshot.design_id == design_id)
        .order_by(EstimateSnapshot.version.desc())
        .limit(1)
    )


async def estimate_state(
    session: AsyncSession, project: Project, design: Design
) -> tuple[EstimateSnapshot | None, bool]:
    """(latest finalised snapshot, stale)."""
    snap = await latest_snapshot(session, design.id)
    if snap is None:
        return None, False
    inputs = await estimate_inputs(session, project, design)
    stale = inputs is None or inputs_fingerprint(inputs) != snap.fingerprint
    return snap, stale


def _not_ready() -> Exception:
    return conflict(
        "parts_not_confirmed",
        "Please confirm the parts of your house first, then we can work out the costs.",
    )


async def live_estimate(session: AsyncSession, project: Project, design: Design) -> EstimateOut:
    inputs = await estimate_inputs(session, project, design)
    if inputs is None:
        raise _not_ready()
    estimate = costing.compute_estimate(inputs)
    snap = await latest_snapshot(session, design.id)
    return EstimateOut(
        id=snap.id if snap else None,
        version=snap.version if snap else None,
        finalised=snap is not None,
        stale=snap is not None and snap.fingerprint != inputs_fingerprint(inputs),
        estimate=estimate,
    )


async def finalise(session: AsyncSession, project: Project, design: Design) -> EstimateOut:
    inputs = await estimate_inputs(session, project, design)
    if inputs is None:
        raise _not_ready()
    if not project.scale_confirmed:
        raise conflict(
            "size_not_confirmed",
            "Please confirm the size of your house before finalising the estimate.",
        )
    if not inputs.assignments:
        raise conflict("no_materials", "Choose at least one material before finalising.")
    estimate = costing.compute_estimate(inputs)
    fp = inputs_fingerprint(inputs)
    snap = await latest_snapshot(session, design.id)
    if snap is not None and snap.fingerprint == fp:  # nothing changed: same version
        return EstimateOut(
            id=snap.id, version=snap.version, finalised=True, stale=False, estimate=estimate
        )
    version = (
        await session.scalar(
            select(func.coalesce(func.max(EstimateSnapshot.version), 0)).where(
                EstimateSnapshot.design_id == design.id
            )
        )
        or 0
    ) + 1
    snap = EstimateSnapshot(
        design_id=design.id,
        version=version,
        fingerprint=fp,
        payload=estimate.model_dump(mode="json"),
        grand_total=estimate.grand_total,
    )
    session.add(snap)
    proj.touch(project)
    await session.commit()
    return EstimateOut(id=snap.id, version=version, finalised=True, stale=False, estimate=estimate)


# ---------------------------------------------------------------- render fingerprint


# what a material looks like; prices, pack sizes, coverage and wastage never change the picture
LOOK_FIELDS = {"id", "name", "category", "description", "colorable", "default_color", "swatch"}


async def render_fingerprint(session: AsyncSession, project: Project, design: Design) -> str:
    """Inputs of a redesign image: photo, parts, this design's choices and their materials.
    Scale and prices are deliberately excluded (they never change the picture)."""
    working = (
        await session.get(ImageRow, project.working_image_id) if project.working_image_id else None
    )
    regions = await proj.approved_regions(session, project)
    assignments = await assignments_of(session, design.id)
    catalogue = get_catalogue()
    used = sorted({a.material_id for a in assignments})
    return fingerprint(
        "render-v2",
        working.sha256 if working else None,
        sorted(
            ({"id": r.id, "label": r.label, "polygon": r.polygon} for r in regions),
            key=lambda r: r["id"],
        ),
        [a.model_dump(mode="json") for a in assignments],
        [catalogue[m].model_dump(mode="json", include=LOOK_FIELDS) for m in used if m in catalogue],
    )
