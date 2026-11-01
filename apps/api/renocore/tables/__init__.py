"""SQLAlchemy ORM models. Ids are UUID strings."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

JsonB = JSON().with_variant(JSONB(), "postgresql")


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


def _id() -> Mapped[str]:
    return mapped_column(String(36), primary_key=True, default=new_id)


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


def _updated() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


def _fk(target: str, nullable: bool = False, ondelete: str = "CASCADE") -> Mapped[Any]:
    return mapped_column(
        String(36), ForeignKey(target, ondelete=ondelete), nullable=nullable, index=True
    )


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = _id()
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = _created()


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = _id()
    owner_id: Mapped[str] = _fk("users.id")
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    stage: Mapped[str] = mapped_column(String(32), nullable=False, default="upload")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    measurements: Mapped[dict] = mapped_column(JsonB, nullable=False, default=dict)
    # current photo (ids of rows in `images`; not FKs to avoid a cycle)
    original_image_id: Mapped[str | None] = mapped_column(String(36))
    working_image_id: Mapped[str | None] = mapped_column(String(36))
    photo_checks: Mapped[dict | None] = mapped_column(JsonB)  # PhotoCheckResult
    whole_photo: Mapped[dict | None] = mapped_column(JsonB)  # WholePhotoAnswers (C1)
    verdict: Mapped[dict | None] = mapped_column(JsonB)  # PhotoVerdict
    verdict_overridden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    regions_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    regions_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scale: Mapped[dict | None] = mapped_column(JsonB)  # ScaleResult
    scale_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    extras: Mapped[dict] = mapped_column(JsonB, nullable=False, default=dict)  # Extras
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class ImageRow(Base):
    __tablename__ = "images"
    id: Mapped[str] = _id()
    project_id: Mapped[str] = _fk("projects.id")
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    path: Mapped[str] = mapped_column(String(512), nullable=False)  # storage key
    content_type: Mapped[str] = mapped_column(String(64), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = _created()


class RegionRow(Base):
    __tablename__ = "regions"
    id: Mapped[str] = _id()
    project_id: Mapped[str] = _fk("projects.id")
    image_id: Mapped[str | None] = mapped_column(String(36))  # working image it belongs to
    label: Mapped[str] = mapped_column(String(16), nullable=False)
    polygon: Mapped[list] = mapped_column(JsonB, nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="gemini")
    label_confidence: Mapped[float | None] = mapped_column(Float)
    needs_check: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    checked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    proposed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    crop_image_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class MaterialAdviceRow(Base):
    __tablename__ = "material_advice"
    __table_args__ = (UniqueConstraint("region_id"),)
    id: Mapped[str] = _id()
    project_id: Mapped[str] = _fk("projects.id")
    region_id: Mapped[str] = _fk("regions.id")
    region_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JsonB, nullable=False)  # MaterialAdvice
    created_at: Mapped[datetime] = _created()


class Design(Base):
    __tablename__ = "designs"
    id: Mapped[str] = _id()
    project_id: Mapped[str] = _fk("projects.id")
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class DesignAssignment(Base):
    __tablename__ = "design_assignments"
    __table_args__ = (UniqueConstraint("design_id", "region_id"),)
    id: Mapped[str] = _id()
    design_id: Mapped[str] = _fk("designs.id")
    region_id: Mapped[str] = _fk("regions.id")
    material_id: Mapped[str] = mapped_column(String(64), nullable=False)
    color: Mapped[str | None] = mapped_column(String(16))


class Render(Base):
    __tablename__ = "renders"
    id: Mapped[str] = _id()
    design_id: Mapped[str] = _fk("designs.id")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    image_id: Mapped[str | None] = mapped_column(String(36))
    zone_map_image_id: Mapped[str | None] = mapped_column(String(36))
    qa: Mapped[dict | None] = mapped_column(JsonB)  # QAResult
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    user_note: Mapped[str | None] = mapped_column(Text)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    accepted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    job_id: Mapped[str | None] = mapped_column(String(36))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class RateOverrideRow(Base):
    __tablename__ = "rate_overrides"
    __table_args__ = (UniqueConstraint("project_id", "material_id"),)
    id: Mapped[str] = _id()
    project_id: Mapped[str] = _fk("projects.id")
    material_id: Mapped[str] = mapped_column(String(64), nullable=False)
    material_rate: Mapped[float | None] = mapped_column(Float)
    labour_rate: Mapped[float | None] = mapped_column(Float)


class EstimateSnapshot(Base):
    """A finalised, numbered estimate version (never overwritten)."""

    __tablename__ = "estimates"
    __table_args__ = (UniqueConstraint("design_id", "version"),)
    id: Mapped[str] = _id()
    design_id: Mapped[str] = _fk("designs.id")
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JsonB, nullable=False)  # Estimate
    grand_total: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = _created()


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[str] = _id()
    design_id: Mapped[str] = _fk("designs.id")
    estimate_id: Mapped[str] = _fk("estimates.id")
    render_id: Mapped[str] = _fk("renders.id")
    estimate_version: Mapped[int] = mapped_column(Integer, nullable=False)
    path: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = _created()


class AICall(Base):
    __tablename__ = "ai_calls"
    id: Mapped[str] = _id()
    project_id: Mapped[str | None] = _fk("projects.id", nullable=True)
    job_id: Mapped[str | None] = mapped_column(String(36))
    step: Mapped[str] = mapped_column(String(4), nullable=False)
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str | None] = mapped_column(String(32))
    input_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    output: Mapped[dict | None] = mapped_column(JsonB)
    confidence: Mapped[float | None] = mapped_column(Float)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[float | None] = mapped_column(Float)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    request_id: Mapped[str | None] = mapped_column(String(128))
    cached: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()


class JobRun(Base):
    """Our own job status table behind JobOut (Procrastinate keeps its own queue tables)."""

    __tablename__ = "job_runs"
    __table_args__ = (Index("ix_job_runs_idem_key_status", "idem_key", "status"),)
    id: Mapped[str] = _id()
    project_id: Mapped[str] = _fk("projects.id")
    design_id: Mapped[str | None] = mapped_column(String(36))
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    step: Mapped[str | None] = mapped_column(String(120))
    error: Mapped[str | None] = mapped_column(Text)
    idem_key: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[dict] = mapped_column(JsonB, nullable=False, default=dict)
    queue_job_id: Mapped[int | None] = mapped_column(Integer)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


ALL_TABLES = [t.name for t in Base.metadata.sorted_tables]
