"""AI contracts: provider interface and call tracing."""

from datetime import datetime
from typing import Literal, Protocol

from PIL.Image import Image
from pydantic import BaseModel

from app.domain.models import (
    LabelAnswer,
    Material,
    MaterialAdvice,
    QAResult,
    Region,
    SegmentCandidate,
    WholePhotoAnswers,
    Zone,
)


class GeminiSegment(BaseModel):
    """Raw Gemini segmentation item: box_2d is [y0, x0, y1, x1] normalised to 0-1000."""

    label: str
    box_2d: list[int]
    mask: str  # base64 PNG probability map (may carry a data: prefix)


class AICallRecord(BaseModel):
    step: Literal["C1", "C2", "C3", "C4", "C5", "C6"]
    provider: Literal["gemini", "jev", "fake"]
    model: str
    prompt_version: str | None = None
    input_hash: str
    output: dict | None = None
    confidence: float | None = None
    latency_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    attempts: int = 1
    request_id: str | None = None
    cached: bool = False
    error: str | None = None
    created_at: datetime | None = None


class AICallRecorder(Protocol):
    async def record(self, call: AICallRecord) -> None: ...


class AIProvider(Protocol):
    """One method per AI call."""

    async def whole_photo(self, photo: Image) -> WholePhotoAnswers:
        """C1 - Jev whole-photo decisions."""
        ...

    async def segment(self, photo: Image) -> list[SegmentCandidate]:
        """C2 - Gemini segmentation, masks already converted to polygons."""
        ...

    async def label_regions(self, photo: Image, regions: list[Region]) -> dict[str, LabelAnswer]:
        """C3 - Jev label per region (keyed by region id)."""
        ...

    async def material_advice(
        self, photo: Image, regions: list[Region], materials: dict[str, Material]
    ) -> list[MaterialAdvice]:
        """C4 - Jev material suggestions per region."""
        ...

    async def generate_redesign(
        self,
        photo: Image,
        zone_map: Image,
        zones: list[Zone],
        materials: dict[str, Material],
        user_note: str | None = None,
        fix_notes: list[str] | None = None,
    ) -> Image:
        """C5 - Gemini redesign (raw model output, not yet composited)."""
        ...

    async def check_render(
        self,
        original: Image,
        result: Image,
        zone_map: Image,
        zones: list[Zone],
        materials: dict[str, Material],
    ) -> QAResult:
        """C6 - Jev design check."""
        ...
