"""Live smoke tests for C1-C6 against the real Gemini and Jev APIs.

Opt-in only: `RUN_LIVE=1 uv run pytest -m live tests/live`. Needs GEMINI_API_KEY and JEV_API_KEY.
Results are cached under STORAGE_ROOT/ai_cache, so re-runs don't spend quota again.
"""

import json
import os
from pathlib import Path

import pytest

from app import imaging
from app.ai import RealProvider, apply_labels, photo_verdict, render_design
from app.config import ROOT_DIR, get_settings
from app.domain.ai import AICallRecord
from app.domain.models import Assignment, Material, Region

pytestmark = pytest.mark.live

SETTINGS = get_settings()
SAMPLES = sorted((ROOT_DIR / "samples").glob("*.jpg"))[:3]

if os.environ.get("RUN_LIVE") != "1":
    pytest.skip("live tests need RUN_LIVE=1", allow_module_level=True)
if not (SETTINGS.gemini_api_key and SETTINGS.jev_api_key):
    pytest.skip("live tests need GEMINI_API_KEY and JEV_API_KEY", allow_module_level=True)
if not SAMPLES:
    pytest.skip("no sample photos in samples/", allow_module_level=True)


class ListRecorder:
    def __init__(self) -> None:
        self.calls: list[AICallRecord] = []

    async def record(self, call: AICallRecord) -> None:
        self.calls.append(call)


def load_materials() -> dict[str, Material]:
    path = SETTINGS.seed_dir / "materials.json"
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data["materials"] if isinstance(data, dict) else data
        return {m["id"]: Material.model_validate(m) for m in items}
    base = dict(
        category="paint",
        pricing_unit="litre",
        measure_basis="area",
        wastage_pct=5,
        material_rate=300,
        labour_rate=15,
        weather_resistance="high",
        durability="8-10 years",
        maintenance="Wash once a year.",
    )
    return {
        "beige_paint": Material(
            id="beige_paint",
            name="Beige exterior paint",
            description="smooth weatherproof acrylic paint",
            applicable_labels=["wall", "parapet", "pillar"],
            colorable=True,
            default_color="#e8d8b0",
            swatch="beige_paint.png",
            **base,
        ),
        "grey_stone": Material(
            id="grey_stone",
            name="Grey natural stone cladding",
            description="split-face stone tiles",
            applicable_labels=["wall", "pillar"],
            swatch="grey_stone.png",
            **base,
        ),
    }


def working(path: Path):
    return imaging.make_working_copy(imaging.load_upload(path.read_bytes()))


@pytest.fixture(scope="module")
def provider_and_recorder():
    recorder = ListRecorder()
    settings = SETTINGS.model_copy(update={"ai_provider": "real"})
    return RealProvider(settings, recorder), recorder


@pytest.mark.parametrize("sample", SAMPLES, ids=lambda p: p.stem)
async def test_c1_whole_photo(provider_and_recorder, sample):
    provider, recorder = provider_and_recorder
    photo = working(sample)
    answers = await provider.whole_photo(photo)
    assert 0 <= answers.is_residential_exterior <= 1
    assert 0 <= answers.usability <= 4
    if answers.main_door is not None:
        b = answers.main_door.box
        assert 0 <= b.left < b.right <= 1 and 0 <= b.top < b.bottom <= 1
    verdict = photo_verdict(imaging.check_photo(photo), answers)
    assert verdict.status in {"pass", "warn", "reject"}
    assert recorder.calls[-1].step == "C1" and recorder.calls[-1].error is None


@pytest.mark.parametrize("sample", SAMPLES, ids=lambda p: p.stem)
async def test_c2_c3_c4(provider_and_recorder, sample):
    provider, _ = provider_and_recorder
    photo = working(sample)
    candidates = await provider.segment(photo)
    assert any(c.label_hint == "wall" for c in candidates)
    regions = [
        Region(id=f"r{i}", label=c.label_hint, polygon=c.polygon) for i, c in enumerate(candidates)
    ]
    answers = await provider.label_regions(photo, regions)
    assert answers
    final = apply_labels(regions, answers, SETTINGS.region_confidence_threshold)
    assert final
    advice = await provider.material_advice(photo, final, load_materials())
    assert all(len(a.recommended) <= 2 for a in advice)


async def test_c5_c6_render(provider_and_recorder):
    provider, recorder = provider_and_recorder
    photo = working(SAMPLES[0])
    candidates = await provider.segment(photo)
    regions = [
        Region(id=f"r{i}", label=c.label_hint, polygon=c.polygon) for i, c in enumerate(candidates)
    ]
    materials = load_materials()
    walls = [r for r in regions if r.label == "wall"]
    wall_material = next(m for m in materials.values() if "wall" in m.applicable_labels)
    outcome = await render_design(
        provider,
        photo,
        regions,
        [Assignment(region_id=r.id, material_id=wall_material.id) for r in walls],
        materials,
        None,
        max_auto_regenerate=1,
        qa_threshold=SETTINGS.render_qa_threshold,
    )
    assert outcome.image.size == photo.size
    assert 1 <= outcome.attempts <= 2
    assert {"C5", "C6"} <= {c.step for c in recorder.calls}
    out_dir = SETTINGS.storage_root / "live_renders"
    out_dir.mkdir(parents=True, exist_ok=True)
    outcome.image.save(out_dir / f"{SAMPLES[0].stem}_render.png")
