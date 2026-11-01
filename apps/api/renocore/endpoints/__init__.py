"""HTTP API. Paths, methods, request and response models are the contract with
the frontend. It may be split this into modules but must keep the contract unchanged.
All paths are mounted under /api.

Handlers are thin: owner checks, gates and staleness live in renocore.operations. Dependencies read
the session cookie from the request (not a Cookie() parameter) so the OpenAPI stays unchanged.
"""

from fastapi import APIRouter, Depends, File, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from renocore.blobstore import get_storage
from renocore.database import get_session
from renocore.identity import (
    authenticate,
    clear_session_cookie,
    current_user,
    register_user,
    set_session_cookie,
)
from renocore.operations import budgets as est
from renocore.operations import exports as reports_svc
from renocore.operations import job_runner as jobs_svc
from renocore.operations import lifecycle as workflow
from renocore.operations import lineage as trace
from renocore.operations import makeovers as designs_svc
from renocore.operations import workspaces as proj
from renocore.operations.failures import invalid
from renocore.operations.materials_catalog import get_catalogue, swatch_url
from renocore.schemas.contracts import (
    AICallOut,
    AssignmentsPut,
    Credentials,
    DesignCreate,
    DesignOut,
    DesignUpdate,
    EstimateOut,
    JobAccepted,
    JobOut,
    MaterialAdviceOut,
    MaterialOut,
    PhotoUploadResult,
    ProjectCreate,
    ProjectOut,
    ProjectSummary,
    ProjectUpdate,
    RatesOut,
    RatesPut,
    RegionsOut,
    RegionsPut,
    RenderOut,
    RenderRequest,
    RenderStarted,
    ReportOut,
    ScaleConfirm,
    ScaleOut,
    UserOut,
)
from renocore.schemas.entities import MaterialAdvice
from renocore.settings import get_settings
from renocore.tables import AICall, MaterialAdviceRow, RegionRow, User

router = APIRouter(prefix="/api")

Session = Depends(get_session)
CurrentUser = Depends(current_user)


def _user_out(user: User) -> UserOut:
    return UserOut(id=user.id, email=user.email)


# ---------------------------------------------------------------- auth (cookie session)
@router.post("/auth/register", response_model=UserOut, tags=["auth"])
async def register(
    body: Credentials, response: Response, session: AsyncSession = Session
) -> UserOut:
    user = await register_user(session, body.email, body.password)
    set_session_cookie(response, user.id, get_settings())
    return _user_out(user)


@router.post("/auth/login", response_model=UserOut, tags=["auth"])
async def login(body: Credentials, response: Response, session: AsyncSession = Session) -> UserOut:
    user = await authenticate(session, body.email, body.password)
    set_session_cookie(response, user.id, get_settings())
    return _user_out(user)


@router.post("/auth/logout", status_code=204, tags=["auth"])
async def logout(response: Response) -> None:
    clear_session_cookie(response, get_settings())


@router.get("/auth/me", response_model=UserOut, tags=["auth"])
async def me(user: User = CurrentUser) -> UserOut:
    return _user_out(user)


# ---------------------------------------------------------------- projects
@router.get("/projects", response_model=list[ProjectSummary], tags=["projects"])
async def list_projects(
    user: User = CurrentUser, session: AsyncSession = Session
) -> list[ProjectSummary]:
    return [
        proj.project_summary(p, await designs_svc.has_current_report(session, p))
        for p in await workflow.list_projects(session, user)
    ]


@router.post("/projects", response_model=ProjectOut, status_code=201, tags=["projects"])
async def create_project(
    body: ProjectCreate, user: User = CurrentUser, session: AsyncSession = Session
) -> ProjectOut:
    return await workflow.create_project(session, user, body)


@router.get("/projects/{project_id}", response_model=ProjectOut, tags=["projects"])
async def get_project(
    project_id: str, user: User = CurrentUser, session: AsyncSession = Session
) -> ProjectOut:
    project = await proj.get_project(session, user, project_id)
    return await proj.project_out(session, project)


@router.patch("/projects/{project_id}", response_model=ProjectOut, tags=["projects"])
async def update_project(
    project_id: str, body: ProjectUpdate, user: User = CurrentUser, session: AsyncSession = Session
) -> ProjectOut:
    return await workflow.update_project(session, user, project_id, body)


@router.delete("/projects/{project_id}", status_code=204, tags=["projects"])
async def delete_project(
    project_id: str, user: User = CurrentUser, session: AsyncSession = Session
) -> None:
    await workflow.delete_project(session, user, project_id)


# ---------------------------------------------------------------- photo (S1, G1)
@router.post(
    "/projects/{project_id}/photo",
    response_model=PhotoUploadResult,
    status_code=202,
    tags=["photo"],
)
async def upload_photo(
    project_id: str,
    file: UploadFile = File(...),
    user: User = CurrentUser,
    session: AsyncSession = Session,
) -> PhotoUploadResult:
    """Instant code checks (hard failures -> 422 ApiError), then enqueue analysis."""
    limit = get_settings().max_upload_bytes
    data = await file.read(limit + 1)
    if len(data) > limit:
        mb = limit // (1024 * 1024)
        raise invalid("too_large", f"This photo is too large. Please upload one under {mb} MB.")
    return await workflow.upload_photo(session, user, project_id, data)


@router.post("/projects/{project_id}/photo/continue", response_model=ProjectOut, tags=["photo"])
async def continue_with_warning(
    project_id: str, user: User = CurrentUser, session: AsyncSession = Session
) -> ProjectOut:
    """G1: user chooses 'Use this photo' on a warning."""
    return await workflow.continue_with_warning(session, user, project_id)


# ---------------------------------------------------------------- regions (G2)
@router.get("/projects/{project_id}/regions", response_model=RegionsOut, tags=["regions"])
async def get_regions(
    project_id: str, user: User = CurrentUser, session: AsyncSession = Session
) -> RegionsOut:
    project = await proj.get_project(session, user, project_id)
    return await workflow.get_regions(session, project)


@router.put("/projects/{project_id}/regions", response_model=RegionsOut, tags=["regions"])
async def put_regions(
    project_id: str, body: RegionsPut, user: User = CurrentUser, session: AsyncSession = Session
) -> RegionsOut:
    """Save edits. Editing after approval reopens G2 and marks dependants stale."""
    return await workflow.put_regions(session, user, project_id, body)


@router.post("/projects/{project_id}/regions/approve", response_model=ProjectOut, tags=["regions"])
async def approve_regions(
    project_id: str, user: User = CurrentUser, session: AsyncSession = Session
) -> ProjectOut:
    """409 if checks are pending. Starts relabel (if needed) and material advice jobs."""
    return await workflow.approve_regions(session, user, project_id)


# ---------------------------------------------------------------- scale (G3)
@router.get("/projects/{project_id}/scale", response_model=ScaleOut, tags=["scale"])
async def get_scale(
    project_id: str, user: User = CurrentUser, session: AsyncSession = Session
) -> ScaleOut:
    project = await proj.get_project(session, user, project_id)
    return workflow.scale_out(project)


@router.post("/projects/{project_id}/scale/confirm", response_model=ScaleOut, tags=["scale"])
async def confirm_scale(
    project_id: str, body: ScaleConfirm, user: User = CurrentUser, session: AsyncSession = Session
) -> ScaleOut:
    return await workflow.confirm_scale(session, user, project_id, body)


# ---------------------------------------------------------------- materials
@router.get("/materials", response_model=list[MaterialOut], tags=["materials"])
async def list_materials() -> list[MaterialOut]:
    return [
        MaterialOut(**m.model_dump(), swatch_url=swatch_url(m)) for m in get_catalogue().values()
    ]


@router.get(
    "/projects/{project_id}/material-advice",
    response_model=MaterialAdviceOut,
    tags=["materials"],
)
async def get_material_advice(
    project_id: str, user: User = CurrentUser, session: AsyncSession = Session
) -> MaterialAdviceOut:
    project = await proj.get_project(session, user, project_id)
    rows = await session.scalars(
        select(MaterialAdviceRow)
        .join(RegionRow, RegionRow.id == MaterialAdviceRow.region_id)
        .where(MaterialAdviceRow.project_id == project.id, RegionRow.active.is_(True))
        .order_by(RegionRow.position)
    )
    advice = [MaterialAdvice.model_validate(r.payload) for r in rows]
    busy = await jobs_svc.has_active(session, project.id, "material_advice")
    return MaterialAdviceOut(ready=project.regions_approved and not busy, advice=advice)


# ---------------------------------------------------------------- designs
@router.get("/projects/{project_id}/designs", response_model=list[DesignOut], tags=["designs"])
async def list_designs(
    project_id: str, user: User = CurrentUser, session: AsyncSession = Session
) -> list[DesignOut]:
    project = await proj.get_project(session, user, project_id)
    return await designs_svc.list_designs(session, project)


@router.post(
    "/projects/{project_id}/designs", response_model=DesignOut, status_code=201, tags=["designs"]
)
async def create_design(
    project_id: str, body: DesignCreate, user: User = CurrentUser, session: AsyncSession = Session
) -> DesignOut:
    return await designs_svc.create_design(session, user, project_id, body)


@router.put("/designs/{design_id}/assignments", response_model=DesignOut, tags=["designs"])
async def put_assignments(
    design_id: str, body: AssignmentsPut, user: User = CurrentUser, session: AsyncSession = Session
) -> DesignOut:
    return await designs_svc.put_assignments(session, user, design_id, body)


@router.patch("/designs/{design_id}", response_model=DesignOut, tags=["designs"])
async def update_design(
    design_id: str, body: DesignUpdate, user: User = CurrentUser, session: AsyncSession = Session
) -> DesignOut:
    """Rename a design."""
    return await designs_svc.update_design(session, user, design_id, body)


@router.delete("/designs/{design_id}", status_code=204, tags=["designs"])
async def delete_design(
    design_id: str, user: User = CurrentUser, session: AsyncSession = Session
) -> None:
    await designs_svc.delete_design(session, user, design_id)


# ---------------------------------------------------------------- renders (G4)
@router.post(
    "/designs/{design_id}/render", response_model=RenderStarted, status_code=202, tags=["renders"]
)
async def start_render(
    design_id: str, body: RenderRequest, user: User = CurrentUser, session: AsyncSession = Session
) -> RenderStarted:
    """'Create my new look' or 'Change something' (with note)."""
    return await designs_svc.start_render(session, user, design_id, body.note)


@router.get("/designs/{design_id}/render", response_model=RenderOut | None, tags=["renders"])
async def get_render(
    design_id: str, user: User = CurrentUser, session: AsyncSession = Session
) -> RenderOut | None:
    return await designs_svc.get_render(session, user, design_id)


@router.post("/renders/{render_id}/accept", response_model=RenderOut, tags=["renders"])
async def accept_render(
    render_id: str, user: User = CurrentUser, session: AsyncSession = Session
) -> RenderOut:
    return await designs_svc.accept_render(session, user, render_id)


# ---------------------------------------------------------------- estimates (G5)
@router.get("/designs/{design_id}/estimate", response_model=EstimateOut, tags=["estimates"])
async def get_estimate(
    design_id: str, user: User = CurrentUser, session: AsyncSession = Session
) -> EstimateOut:
    """Always computed live from current inputs; flags provisional/stale."""
    design, project = await proj.get_design(session, user, design_id)
    return await est.live_estimate(session, project, design)


@router.post(
    "/designs/{design_id}/estimate/finalise", response_model=EstimateOut, tags=["estimates"]
)
async def finalise_estimate(
    design_id: str, user: User = CurrentUser, session: AsyncSession = Session
) -> EstimateOut:
    design, project = await proj.get_design(session, user, design_id, for_update=True)
    return await est.finalise(session, project, design)


@router.get("/projects/{project_id}/rates", response_model=RatesOut, tags=["estimates"])
async def get_rates(
    project_id: str, user: User = CurrentUser, session: AsyncSession = Session
) -> RatesOut:
    project = await proj.get_project(session, user, project_id)
    return await est.get_rates(session, project)


@router.put("/projects/{project_id}/rates", response_model=RatesOut, tags=["estimates"])
async def put_rates(
    project_id: str, body: RatesPut, user: User = CurrentUser, session: AsyncSession = Session
) -> RatesOut:
    project = await proj.get_project(session, user, project_id, for_update=True)
    return await est.put_rates(session, project, body)


# ---------------------------------------------------------------- reports
@router.post(
    "/designs/{design_id}/report", response_model=JobAccepted, status_code=202, tags=["reports"]
)
async def create_report(
    design_id: str, user: User = CurrentUser, session: AsyncSession = Session
) -> JobAccepted:
    """409 unless the render is accepted and the estimate finalised and not stale."""
    return await reports_svc.create_report(session, user, design_id)


@router.get("/designs/{design_id}/reports", response_model=list[ReportOut], tags=["reports"])
async def list_reports(
    design_id: str, user: User = CurrentUser, session: AsyncSession = Session
) -> list[ReportOut]:
    return await reports_svc.list_reports(session, user, design_id)


@router.get("/reports/{report_id}/download", tags=["reports"])
async def download_report(
    report_id: str, user: User = CurrentUser, session: AsyncSession = Session
):
    """application/pdf"""
    data, filename = await reports_svc.download(session, user, report_id)
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------- jobs, images, trace
@router.get("/jobs/{job_id}", response_model=JobOut, tags=["jobs"])
async def get_job(job_id: str, user: User = CurrentUser, session: AsyncSession = Session) -> JobOut:
    return jobs_svc.job_out(await proj.get_job(session, user, job_id))


@router.get("/images/{image_id}", tags=["images"])
async def get_image(image_id: str, user: User = CurrentUser, session: AsyncSession = Session):
    """Serves stored images (owner-checked)."""
    row = await proj.get_image(session, user, image_id)
    data = await get_storage().get(row.path)
    return Response(
        content=data,
        media_type=row.content_type,
        headers={"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/projects/{project_id}/ai-calls", response_model=list[AICallOut], tags=["trace"])
async def list_ai_calls(
    project_id: str, user: User = CurrentUser, session: AsyncSession = Session
) -> list[AICallOut]:
    project = await proj.get_project(session, user, project_id)
    rows = await session.scalars(
        select(AICall).where(AICall.project_id == project.id).order_by(AICall.created_at)
    )
    settings = get_settings()
    catalogue = get_catalogue()
    out: list[AICallOut] = []
    for r in rows:
        stage, title, summary = trace.describe(
            r.step,
            r.output,
            r.error is None,
            catalogue,
            settings.region_confidence_threshold,
            settings.render_qa_threshold,
        )
        out.append(
            AICallOut(
                id=r.id,
                step=r.step,
                stage=stage,
                title=title,
                summary=summary,
                ok=r.error is None,
                attention=r.error is None and trace.needs_attention(r.step, summary),
                new_run=trace.starts_run(r.step, r.output),
                provider=r.provider,
                model=r.model,
                latency_ms=r.latency_ms,
                cost_usd=r.cost_usd,
                confidence=r.confidence,
                attempts=r.attempts,
                cached=r.cached,
                created_at=r.created_at,
            )
        )
    return out
