"""Configurable AIProvider test double for the API tests.

Only the model calls (C1-C6) are faked; the real AI rules (verdict, labels, proposals) and the
real render loop (renocore.vision.render_design) run on top of it. Imaging and estimation are real.
Unlike renocore.vision.FakeProvider (recorded fixtures), this one lets a test pick the scenario
(warn / reject photo, unsure labels, QA failures, provider errors) and counts calls.
"""

import time
from dataclasses import dataclass, field

from PIL import Image as PILImage
from PIL.Image import Image

from renocore import pixels
from renocore.schemas.entities import (
    BoxFraction,
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
from renocore.schemas.vision_io import AICallRecord, AICallRecorder

# ---------------------------------------------------------------- provider


def _box(left: float, top: float, right: float, bottom: float) -> BoxResult:
    return BoxResult(
        box=BoxFraction(top=top, bottom=bottom, left=left, right=right), confidence=0.9
    )


# fractions of the photo: (label_hint, left, top, right, bottom)
LAYOUT = [
    ("wall", 0.10, 0.20, 0.90, 0.90),
    ("door", 0.45, 0.60, 0.55, 0.90),
    ("window", 0.20, 0.35, 0.30, 0.50),
    ("window", 0.70, 0.35, 0.80, 0.50),
    ("pillar", 0.12, 0.30, 0.16, 0.90),
    ("railing", 0.30, 0.40, 0.70, 0.46),
]


@dataclass
class FakeProvider:
    """Configurable AIProvider. `scenario` drives C1: pass | warn | reject."""

    recorder: AICallRecorder | None = None
    scenario: str = "pass"
    unsure_labels: tuple[str, ...] = ("pillar",)  # answered with low confidence
    gate_visible: float = 0.8
    door_agrees: bool = True
    windows_alike: bool = True  # two windows of equal height (window-based size fallback)
    qa_failures: int = 0  # how many renders fail QA before passing
    fail: dict[str, int] = field(default_factory=dict)  # method -> raise this many times
    calls: dict[str, int] = field(default_factory=dict)
    advice_requests: list[list[str]] = field(default_factory=list)  # region ids per C4 call

    async def _enter(self, name: str, step: str, output: dict | None = None) -> None:
        self.calls[name] = self.calls.get(name, 0) + 1
        error = None
        if self.fail.get(name, 0) > 0:
            self.fail[name] -= 1
            error = "simulated provider failure"
        if self.recorder is not None:
            await self.recorder.record(
                AICallRecord(
                    step=step,  # type: ignore[arg-type]
                    provider="fake",
                    model="fake-1",
                    input_hash=f"{name}-{self.calls[name]}",
                    output=output,
                    confidence=0.9,
                    latency_ms=1,
                    error=error,
                )
            )
        if error:
            raise RuntimeError(error)

    async def whole_photo(self, photo: Image) -> WholePhotoAnswers:
        await self._enter("whole_photo", "C1")
        start = time.perf_counter()
        door = LAYOUT[1]
        door_box = _box(door[1], door[2], door[3], door[4] if self.door_agrees else 0.99)
        answers = WholePhotoAnswers(
            is_residential_exterior=0.95,
            building_type=ChoiceResult(choice="independent_house", confidence=0.9),
            view_angle=ChoiceResult(choice="straight_on", confidence=0.9),
            facade_obstructed=0.1,
            usability=3.2,
            door_visible=0.9,
            main_door=door_box,
            floors=ChoiceResult(choice="2", confidence=0.8),
            railing_visible=0.9,
            railing=_box(0.30, 0.40, 0.70, 0.46),
            gate_visible=self.gate_visible,
            gate=_box(0.80, 0.70, 0.98, 0.95),
        )
        if self.scenario == "warn":
            answers.view_angle = ChoiceResult(choice="angled", confidence=0.8)
        elif self.scenario == "reject":
            answers.is_residential_exterior = 0.1
            answers.building_type = ChoiceResult(choice="commercial", confidence=0.8)
        _ = start
        return answers

    async def segment(self, photo: Image) -> list[SegmentCandidate]:
        await self._enter("segment", "C2")
        w, h = photo.size
        out = []
        layout = list(LAYOUT)
        if not self.windows_alike:
            layout[3] = ("window", 0.70, 0.35, 0.80, 0.60)
        for label, left, top, right, bottom in layout:
            poly = [
                (left * w, top * h),
                (right * w, top * h),
                (right * w, bottom * h),
                (left * w, bottom * h),
            ]
            out.append(
                SegmentCandidate(
                    label_hint=label,
                    polygon=poly,
                    box=pixels.polygon_box(poly),
                )
            )
        return out

    async def label_regions(self, photo: Image, regions: list[Region]) -> dict[str, LabelAnswer]:
        await self._enter("label_regions", "C3")
        return {
            r.id: LabelAnswer(
                label=r.label, confidence=0.45 if r.label in self.unsure_labels else 0.92
            )
            for r in regions
        }

    async def material_advice(
        self, photo: Image, regions: list[Region], materials: dict[str, Material]
    ) -> list[MaterialAdvice]:
        await self._enter("material_advice", "C4")
        self.advice_requests.append([r.id for r in regions])
        out = []
        for r in regions:
            fits = [m.id for m in materials.values() if r.label in m.applicable_labels]
            out.append(
                MaterialAdvice(
                    region_id=r.id,
                    recommended=fits[:2],
                    not_ideal={
                        m: "Not ideal here: needs frequent maintenance in rain"
                        for m in fits
                        if materials[m].weather_resistance == "low"
                    },
                    exposed=0.8,
                )
            )
        return out

    async def generate_redesign(
        self,
        photo: Image,
        zone_map: Image,
        zones: list[Zone],
        materials: dict[str, Material],
        user_note: str | None = None,
        fix_notes: list[str] | None = None,
    ) -> Image:
        await self._enter("generate_redesign", "C5")
        self.last_note = user_note
        self.last_fix_notes = fix_notes
        return PILImage.new("RGB", (photo.width // 2, photo.height // 2), (150, 110, 80))

    async def check_render(
        self,
        original: Image,
        result: Image,
        zone_map: Image,
        zones: list[Zone],
        materials: dict[str, Material],
    ) -> QAResult:
        await self._enter("check_render", "C6")
        if self.qa_failures > 0:
            self.qa_failures -= 1
            return QAResult(
                openings_preserved=0.9,
                structure_preserved=0.9,
                zones={z.color_name: 0.3 for z in zones},
                passed=False,
                failed_checks=[
                    "The railing may look slightly different from the material you chose"
                ],
            )
        return QAResult(
            openings_preserved=0.95,
            structure_preserved=0.95,
            zones={z.color_name: 0.9 for z in zones},
            passed=True,
        )
