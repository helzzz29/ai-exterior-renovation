"""Report gate (G4 + G5) and the PDF job."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from renocore.blobstore import get_storage
from renocore.database import session_scope
from renocore.exports import ReportData, ReportPart, build_report_pdf
from renocore.operations import budgets as est
from renocore.operations import job_runner as jobs_svc
from renocore.operations import makeovers as designs_svc
from renocore.operations import workspaces as proj
from renocore.operations.failures import conflict, not_found
from renocore.operations.image_pipeline import run_image_work
from renocore.operations.job_runner import JobCtx
from renocore.operations.materials_catalog import get_catalogue
from renocore.operations.photos import store_bytes
from renocore.schemas.contracts import JobAccepted, ReportOut
from renocore.schemas.entities import FRIENDLY_LABELS, Estimate, PhotoVerdict, QAResult
from renocore.tables import (
    Design,
    EstimateSnapshot,
    ImageRow,
    Project,
    RegionRow,
    Render,
    Report,
    User,
)


def report_out(report: Report) -> ReportOut:
    return ReportOut(
        id=report.id,
        design_id=report.design_id,
        estimate_version=report.estimate_version,
        render_id=report.render_id,
        download_url=f"/api/reports/{report.id}/download",
        created_at=report.created_at,
    )


async def create_report(session: AsyncSession, user: User, design_id: str) -> JobAccepted:
    design, project = await proj.get_design(session, user, design_id, for_update=True)
    render = await designs_svc.latest_render(session, design.id)
    if render is None or render.status != "accepted":
        raise conflict(
            "design_not_accepted", "Please accept your new look before downloading the report."
        )
    if await designs_svc.render_is_stale(session, project, design, render):
        raise conflict(
            "design_changed",
            "This design changed after the picture was made. Create and accept a new look first.",
        )
    snap, stale = await est.estimate_state(session, project, design)
    if snap is None:
        raise conflict(
            "estimate_not_finalised", "Please finalise your estimate before downloading the report."
        )
    if stale:
        raise conflict(
            "estimate_changed",
            "Prices or sizes changed. Review and finalise your estimate to update the report.",
        )
    run, _ = await jobs_svc.enqueue(
        session,
        project_id=project.id,
        design_id=design.id,
        kind="report",
        idem_key=f"report:{design.id}:{snap.id}:{render.id}",
        payload={"design_id": design.id, "render_id": render.id, "estimate_id": snap.id},
    )
    return JobAccepted(job_id=run.id)


async def list_reports(session: AsyncSession, user: User, design_id: str) -> list[ReportOut]:
    design, _ = await proj.get_design(session, user, design_id)
    rows = await session.scalars(
        select(Report).where(Report.design_id == design.id).order_by(Report.created_at.desc())
    )
    return [report_out(r) for r in rows]


async def download(session: AsyncSession, user: User, report_id: str) -> tuple[bytes, str]:
    report = await proj.get_report(session, user, report_id)
    design = await session.get(Design, report.design_id)
    name = "".join(c if c.isalnum() else "-" for c in (design.name if design else "report"))
    try:
        data = await get_storage().get(report.path)
    except Exception as exc:
        raise not_found("report file") from exc
    return data, f"renovation-report-{name.lower()}.pdf"


async def _bytes_of(session: AsyncSession, image_id: str | None) -> bytes | None:
    if not image_id:
        return None
    try:
        row = await session.get(ImageRow, image_id)
        if not row or not row.path:
            return None
        return await get_storage().get(row.path)
    except Exception as exc:
        import logging
        logging.getLogger("renocore.exports").warning(
            "Could not retrieve image bytes for image_id %s: %s", image_id, exc
        )
        return None


async def run_report(ctx: JobCtx) -> None:
    async with session_scope() as session:
        design = await session.get(Design, ctx.payload["design_id"])
        render = await session.get(Render, ctx.payload["render_id"])
        snap = await session.get(EstimateSnapshot, ctx.payload["estimate_id"])
        project = await session.get(Project, ctx.project_id)
        if design is None or render is None or snap is None or project is None:
            return
        estimate = Estimate.model_validate(snap.payload)
        catalogue = get_catalogue()
        parts: list[ReportPart] = []
        for a in await est.assignments_of(session, design.id):
            region = await session.get(RegionRow, a.region_id)
            material = catalogue.get(a.material_id)
            parts.append(
                ReportPart(
                    part=FRIENDLY_LABELS.get(region.label, region.label) if region else "Part",
                    material=material.name if material else a.material_id,
                    color=a.color,
                )
            )
        warnings: list[str] = []
        if project.verdict_overridden and project.verdict:
            verdict = PhotoVerdict.model_validate(project.verdict)
            warnings = [i.message for i in verdict.issues if i.severity == "warn"]
        qa = QAResult.model_validate(render.qa) if render.qa else None
        data = ReportData(
            project_name=project.name,
            created_at=snap.created_at,
            estimate=estimate,
            estimate_version=snap.version,
            design_name=design.name,
            parts=parts,
            original_jpeg=await _bytes_of(session, project.working_image_id),
            redesign_jpeg=await _bytes_of(session, render.image_id),
            photo_warnings=warnings,
            render_notes=list(qa.failed_checks) if qa and not qa.passed else [],
        )
    pdf = await run_image_work(build_report_pdf, data)
    async with session_scope() as session:
        asset = await store_bytes(
            session, ctx.project_id, "report_asset", pdf, 0, 0, "application/pdf", "pdf"
        )
        session.add(
            Report(
                design_id=ctx.payload["design_id"],
                estimate_id=ctx.payload["estimate_id"],
                render_id=ctx.payload["render_id"],
                estimate_version=data.estimate_version,
                path=asset.path,
            )
        )
        await session.commit()
