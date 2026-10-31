"""Deterministic fake AIProvider (AI_PROVIDER=fake): no network, only Pillow.

Used by unit, integration, frontend and end-to-end tests. If a recorded response exists in
`tests/fixtures/ai/<photo key>.<step>.json` it is replayed; otherwise plausible synthetic answers
are produced relative to the image size. The photo key is `photo_key(photo)` (sha256 of pixels).
"""

import hashlib
import json
from pathlib import Path
from typing import Any

from PIL import Image as PILImage
from PIL.Image import Image

from app.ai.rules import advice_from_answers, qa_from_scores
from app.ai.tracing import Tracer
from app.config import Settings
from app.domain.ai import AICallRecord, AICallRecorder
from app.domain.models import (
    OPENING_LABELS,
    BoxFraction,
    BoxPx,
    BoxResult,
    ChoiceResult,
    LabelAnswer,
    Material,
    MaterialAdvice,
    QAResult,
    Region,
    SegmentCandidate,
    WholePhotoAnswers,
    Zone,
)

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "ai"

# Synthetic layout as fractions (x0, y0, x1, y1) of the image.
DOOR = (0.44, 0.65, 0.56, 0.95)
LAYOUT: tuple[tuple[str, tuple[float, float, float, float]], ...] = (
    ("wall", (0.10, 0.55, 0.90, 0.95)),
    ("wall", (0.15, 0.20, 0.85, 0.55)),
    ("parapet", (0.15, 0.15, 0.85, 0.20)),
    ("window", (0.20, 0.62, 0.35, 0.80)),
    ("window", (0.65, 0.62, 0.80, 0.80)),
    ("window", (0.25, 0.28, 0.42, 0.45)),
    ("door", DOOR),
    ("pillar", (0.10, 0.55, 0.14, 0.95)),
    ("pillar", (0.86, 0.55, 0.90, 0.95)),
    ("balcony", (0.55, 0.45, 0.80, 0.55)),
    ("railing", (0.55, 0.38, 0.80, 0.45)),
)
LOW_CONFIDENCE = 0.45


def photo_key(photo: Image) -> str:
    h = hashlib.sha256(f"{photo.mode}:{photo.width}x{photo.height}:".encode())
    h.update(photo.tobytes())
    return h.hexdigest()[:16]


class FakeProvider:
    def __init__(
        self,
        settings: Settings | None = None,
        recorder: AICallRecorder | None = None,
        fixtures_dir: Path = FIXTURES_DIR,
    ) -> None:
        self.settings = settings
        self.tracer = Tracer(recorder)
        self.fixtures_dir = Path(fixtures_dir)
        self.qa_threshold = settings.render_qa_threshold if settings else 0.6

    # ------------------------------------------------------------ helpers

    def _fixture(self, photo: Image, step: str) -> Any | None:
        path = self.fixtures_dir / f"{photo_key(photo)}.{step}.json"
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
        return None

    async def _record(self, step: str, photo: Image, output: dict | None) -> None:
        await self.tracer.record(
            AICallRecord(
                step=step,  # type: ignore[arg-type]
                provider="fake",
                model="fake",
                input_hash=photo_key(photo),
                output=output,
                latency_ms=0,
                cost_usd=0.0,
            )
        )

    # ------------------------------------------------------------ C1-C6

    async def whole_photo(self, photo: Image) -> WholePhotoAnswers:
        recorded = self._fixture(photo, "C1")
        if recorded is not None:
            answers = WholePhotoAnswers.model_validate(recorded)
        else:
            x0, y0, x1, y1 = DOOR
            answers = WholePhotoAnswers(
                is_residential_exterior=0.97,
                building_type=ChoiceResult(
                    choice="independent_house",
                    confidence=0.9,
                    probabilities={"independent_house": 0.9, "bungalow": 0.1},
                ),
                view_angle=ChoiceResult(
                    choice="straight_on", confidence=0.92, probabilities={"straight_on": 0.92}
                ),
                facade_obstructed=0.08,
                usability=3.2,
                door_visible=0.93,
                main_door=BoxResult(
                    box=BoxFraction(top=y0, bottom=y1, left=x0, right=x1), confidence=0.88
                ),
                floors=ChoiceResult(choice="2", confidence=0.9, probabilities={"2": 0.9}),
                railing_visible=0.2,
                railing=None,
                gate_visible=0.1,
                gate=None,
            )
        await self._record("C1", photo, answers.model_dump(mode="json"))
        return answers

    async def segment(self, photo: Image) -> list[SegmentCandidate]:
        recorded = self._fixture(photo, "C2")
        if recorded is not None:
            out = [SegmentCandidate.model_validate(c) for c in recorded]
        else:
            w, h = photo.width, photo.height
            out = []
            for label, (fx0, fy0, fx1, fy1) in LAYOUT:
                box = BoxPx(x0=fx0 * w, y0=fy0 * h, x1=fx1 * w, y1=fy1 * h)
                polygon = [(box.x0, box.y0), (box.x1, box.y0), (box.x1, box.y1), (box.x0, box.y1)]
                out.append(SegmentCandidate(label_hint=label, polygon=polygon, box=box))
        await self._record("C2", photo, {"count": len(out)})
        return out

    async def label_regions(self, photo: Image, regions: list[Region]) -> dict[str, LabelAnswer]:
        recorded = self._fixture(photo, "C3")
        if recorded is not None:
            out = {k: LabelAnswer.model_validate(v) for k, v in recorded.items()}
        else:
            low = next((r.id for r in regions if r.label == "pillar"), None)
            if low is None and regions:
                low = regions[-1].id
            out = {
                r.id: LabelAnswer(
                    label=r.label,
                    confidence=LOW_CONFIDENCE if r.id == low else 0.9,
                    probabilities={r.label: LOW_CONFIDENCE if r.id == low else 0.9},
                )
                for r in regions
            }
        await self._record("C3", photo, {k: v.model_dump() for k, v in out.items()})
        return out

    async def material_advice(
        self, photo: Image, regions: list[Region], materials: dict[str, Material]
    ) -> list[MaterialAdvice]:
        recorded = self._fixture(photo, "C4")
        if recorded is not None:
            out = [MaterialAdvice.model_validate(a) for a in recorded]
        else:
            out = []
            for r in regions:
                if r.label in OPENING_LABELS:
                    continue
                applicable = [m for m in materials.values() if r.label in m.applicable_labels]
                if not applicable:
                    continue
                n = len(applicable)
                probs = {
                    m.id: (0.5 if i == 0 else 0.3 if i == 1 else 0.2 / max(n - 2, 1))
                    for i, m in enumerate(applicable)
                }
                exposed = 0.7 if r.label in {"wall", "parapet", "railing", "gate"} else 0.3
                out.append(advice_from_answers(r.id, probs, exposed, applicable))
        await self._record("C4", photo, {"count": len(out)})
        return out

    async def generate_redesign(
        self,
        photo: Image,
        zone_map: Image,
        zones: list[Zone],
        materials: dict[str, Material],
        user_note: str | None = None,
        fix_notes: list[str] | None = None,
        attempt: int = 0,
        cache_salt: str | None = None,
    ) -> Image:
        tint = zone_map.convert("RGB").resize(photo.size)
        result = PILImage.blend(photo.convert("RGB"), tint, 0.5)
        await self._record("C5", photo, {"zones": len(zones), "attempt": attempt})
        return result

    async def check_render(
        self,
        original: Image,
        result: Image,
        zone_map: Image,
        zones: list[Zone],
        materials: dict[str, Material],
    ) -> QAResult:
        qa = qa_from_scores(
            0.92, 0.94, {z.color_name: 0.9 for z in zones}, zones, materials, self.qa_threshold
        )
        await self._record("C6", original, qa.model_dump())
        return qa
