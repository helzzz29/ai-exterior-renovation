"""HTTP request/response schemas (contract between backend and frontend)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from renocore.schemas.entities import (
    Assignment,
    BoxPx,
    Confidence,
    Estimate,
    Extras,
    Label,
    Material,
    MaterialAdvice,
    Measurements,
    PhotoVerdict,
    Point,
    QAResult,
    RateOverride,
    ReferenceLine,
    RegionSource,
    ScaleMethod,
)

# ---------------------------------------------------------------- auth


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserOut(BaseModel):
    id: str
    email: str


# ---------------------------------------------------------------- jobs

JobKind = Literal["analyze_photo", "relabel_regions", "material_advice", "render", "report"]
JobStatus = Literal["queued", "running", "done", "failed"]


class JobOut(BaseModel):
    id: str
    kind: JobKind
    status: JobStatus
    step: str | None = None  # plain-language progress, e.g. "Finding walls, windows and balconies"
    error: str | None = None


class JobAccepted(BaseModel):
    job_id: str


# ---------------------------------------------------------------- projects

ProjectStage = Literal[
    "upload",  # no photo yet
    "analyzing",  # analysis job running
    "photo_rejected",  # G1 reject: re-upload only
    "photo_warning",  # G1 warn: continue or re-upload
    "regions_review",  # G2
    "scale_review",  # G3
    "designing",  # materials, renders, estimates
]


class ImageOut(BaseModel):
    id: str
    url: str
    width: int
    height: int


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    measurements: Measurements = Measurements()


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    measurements: Measurements | None = None


class ProjectSummary(BaseModel):
    id: str
    name: str
    stage: ProjectStage
    thumbnail_url: str | None = None
    updated_at: datetime
    report_ready: bool = False  # a report matching the current look and estimate exists


class ProjectOut(BaseModel):
    id: str
    name: str
    stage: ProjectStage
    measurements: Measurements
    photo: ImageOut | None = None
    verdict: PhotoVerdict | None = None
    verdict_overridden: bool = False
    regions_approved: bool = False
    scale_confirmed: bool = False
    active_job: JobOut | None = None
    created_at: datetime
    updated_at: datetime


class PhotoUploadResult(BaseModel):
    project: ProjectOut
    job_id: str


# ---------------------------------------------------------------- regions


class RegionOut(BaseModel):
    id: str
    label: Label
    friendly_label: str
    polygon: list[Point]
    source: RegionSource
    needs_check: bool
    checked: bool
    proposed: bool
    crop_url: str | None = None


class RegionIn(BaseModel):
    id: str | None = None  # None = new region drawn by the user
    label: Label
    polygon: list[Point] = Field(min_length=3)
    checked: bool = False
    proposed: bool = False


class RegionsPut(BaseModel):
    regions: list[RegionIn]


class RegionsOut(BaseModel):
    regions: list[RegionOut]
    approved: bool
    pending_checks: int  # needs_check and not yet checked, plus undecided proposals


# ---------------------------------------------------------------- scale


class ScaleOut(BaseModel):
    ft_per_px: float
    method: ScaleMethod
    confidence: Confidence
    facade_width_ft: float | None
    reference_box: BoxPx | None
    explanation: str
    needs_measurement: bool
    confirmed: bool


class ScaleConfirm(BaseModel):
    """Either accept the proposed scale, or supply one measurement."""

    accept: bool = False
    facade_width_ft: float | None = Field(default=None, gt=0)
    facade_height_ft: float | None = Field(default=None, gt=0)
    reference_line: ReferenceLine | None = None


# ---------------------------------------------------------------- materials


class MaterialOut(Material):
    swatch_url: str


class MaterialAdviceOut(BaseModel):
    ready: bool
    advice: list[MaterialAdvice]


# ---------------------------------------------------------------- designs & renders

RenderStatus = Literal["queued", "running", "ready", "accepted", "failed"]


class RenderOut(BaseModel):
    id: str
    status: RenderStatus
    image_url: str | None = None
    qa: QAResult | None = None
    attempts: int = 0
    user_note: str | None = None
    stale: bool = False
    created_at: datetime


class DesignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    copy_from: str | None = None  # design id to duplicate


class DesignUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class DesignOut(BaseModel):
    id: str
    name: str
    assignments: list[Assignment]
    render: RenderOut | None = None
    estimate_stale: bool = False
    estimate_finalised: bool = False
    created_at: datetime


class AssignmentsPut(BaseModel):
    assignments: list[Assignment]


class RenderRequest(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class RenderStarted(BaseModel):
    render: RenderOut
    job_id: str


# ---------------------------------------------------------------- estimates & rates


class EstimateOut(BaseModel):
    id: str | None = None  # None until finalised
    version: int | None = None
    finalised: bool = False
    stale: bool = False
    estimate: Estimate


class RatesOut(BaseModel):
    overrides: list[RateOverride]
    extras: Extras


class RatesPut(BaseModel):
    overrides: list[RateOverride] = []
    extras: Extras = Extras()


# ---------------------------------------------------------------- reports


class ReportOut(BaseModel):
    id: str
    design_id: str
    estimate_version: int
    render_id: str  # the accepted new look the report was built from
    download_url: str
    created_at: datetime


# ---------------------------------------------------------------- trace


class AICallOut(BaseModel):
    id: str
    step: str  # internal step code (C1-C6)
    stage: Literal["photo", "materials", "look"]
    title: str  # plain-language name of the step
    summary: str  # plain-language result of the step
    ok: bool  # False when the call failed and was retried
    attention: bool = False  # the step found something worth looking at
    new_run: bool = False  # first attempt of a new "Create my new look" run
    provider: str
    model: str
    latency_ms: int
    cost_usd: float | None
    confidence: float | None
    attempts: int
    cached: bool
    created_at: datetime


class ApiError(BaseModel):
    code: str
    message: str  # plain-language
