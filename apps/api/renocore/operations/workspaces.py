"""Owner-scoped lookups and ORM -> API serialisation. Other users' resources are 404."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from renocore.operations import job_runner as jobs_svc
from renocore.operations.failures import not_found
from renocore.operations.photos import image_out, image_url
from renocore.schemas.contracts import ProjectOut, ProjectSummary, RegionOut
from renocore.schemas.entities import (
    FRIENDLY_LABELS,
    Measurements,
    PhotoVerdict,
    Region,
    ScaleResult,
)
from renocore.tables import (
    Design,
    ImageRow,
    JobRun,
    Project,
    RegionRow,
    Render,
    Report,
    User,
)

# ---------------------------------------------------------------- owner-scoped access


async def get_project(
    session: AsyncSession, user: User, project_id: str, *, for_update: bool = False
) -> Project:
    project = await session.get(
        Project, project_id, with_for_update=for_update, populate_existing=for_update
    )
    if project is None or project.owner_id != user.id:
        raise not_found("project")
    return project


async def get_design(
    session: AsyncSession, user: User, design_id: str, *, for_update: bool = False
) -> tuple[Design, Project]:
    design = await session.get(Design, design_id)
    if design is None:
        raise not_found("design")
    project = await session.get(
        Project, design.project_id, with_for_update=for_update, populate_existing=for_update
    )
    if project is None or project.owner_id != user.id:
        raise not_found("design")
    return design, project


async def get_render(session: AsyncSession, user: User, render_id: str) -> tuple[Render, Design]:
    render = await session.get(Render, render_id)
    if render is None:
        raise not_found("design picture")
    try:
        design, _ = await get_design(session, user, render.design_id)
    except Exception:
        raise not_found("design picture") from None
    return render, design


async def get_report(session: AsyncSession, user: User, report_id: str) -> Report:
    report = await session.get(Report, report_id)
    if report is None:
        raise not_found("report")
    try:
        await get_design(session, user, report.design_id)
    except Exception:
        raise not_found("report") from None
    return report


async def get_job(session: AsyncSession, user: User, job_id: str) -> JobRun:
    run = await session.get(JobRun, job_id)
    if run is None:
        raise not_found("task")
    project = await session.get(Project, run.project_id)
    if project is None or project.owner_id != user.id:
        raise not_found("task")
    return run


async def get_image(session: AsyncSession, user: User, image_id: str) -> ImageRow:
    row = await session.get(ImageRow, image_id)
    if row is None:
        raise not_found("image")
    project = await session.get(Project, row.project_id)
    if project is None or project.owner_id != user.id:
        raise not_found("image")
    return row


# ---------------------------------------------------------------- domain conversions


def measurements(project: Project) -> Measurements:
    return Measurements.model_validate(project.measurements or {})


def scale_of(project: Project) -> ScaleResult | None:
    return ScaleResult.model_validate(project.scale) if project.scale else None


def to_region(row: RegionRow) -> Region:
    return Region(
        id=row.id,
        label=row.label,  # type: ignore[arg-type]
        polygon=[(float(x), float(y)) for x, y in row.polygon],
        source=row.source,  # type: ignore[arg-type]
        label_confidence=row.label_confidence,
        needs_check=row.needs_check,
        checked=row.checked,
        proposed=row.proposed,
    )


async def active_region_rows(session: AsyncSession, project_id: str) -> list[RegionRow]:
    rows = await session.scalars(
        select(RegionRow)
        .where(RegionRow.project_id == project_id, RegionRow.active.is_(True))
        .order_by(RegionRow.position, RegionRow.created_at)
    )
    return list(rows)


async def approved_regions(session: AsyncSession, project: Project) -> list[Region]:
    """Active, accepted regions (proposals that were never accepted are excluded)."""
    rows = await active_region_rows(session, project.id)
    return [to_region(r) for r in rows if not r.proposed]


def region_out(row: RegionRow) -> RegionOut:
    return RegionOut(
        id=row.id,
        label=row.label,  # type: ignore[arg-type]
        friendly_label=FRIENDLY_LABELS.get(row.label, row.label),
        polygon=[(float(x), float(y)) for x, y in row.polygon],
        source=row.source,  # type: ignore[arg-type]
        needs_check=row.needs_check,
        checked=row.checked,
        proposed=row.proposed,
        crop_url=image_url(row.crop_image_id) if row.crop_image_id else None,
    )


def pending_checks(rows: list[RegionRow]) -> int:
    return sum(1 for r in rows if (r.needs_check and not r.checked) or r.proposed)


async def project_out(session: AsyncSession, project: Project) -> ProjectOut:
    photo = None
    if project.working_image_id:
        row = await session.get(ImageRow, project.working_image_id)
        if row is not None:
            photo = image_out(row)
    active = await jobs_svc.latest_active(session, project.id)
    return ProjectOut(
        id=project.id,
        name=project.name,
        stage=project.stage,  # type: ignore[arg-type]
        measurements=measurements(project),
        photo=photo,
        verdict=PhotoVerdict.model_validate(project.verdict) if project.verdict else None,
        verdict_overridden=project.verdict_overridden,
        regions_approved=project.regions_approved,
        scale_confirmed=project.scale_confirmed,
        active_job=jobs_svc.job_out(active) if active else None,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


def project_summary(project: Project, report_ready: bool = False) -> ProjectSummary:
    return ProjectSummary(
        id=project.id,
        name=project.name,
        stage=project.stage,  # type: ignore[arg-type]
        thumbnail_url=image_url(project.working_image_id) if project.working_image_id else None,
        updated_at=project.updated_at,
        report_ready=report_ready,
    )


def touch(project: Project) -> None:
    """Bump updated_at even when only child rows changed."""
    from renocore.tables import utcnow

    project.updated_at = utcnow()
