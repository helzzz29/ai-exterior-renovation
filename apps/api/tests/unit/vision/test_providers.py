"""get_provider, the fake provider end-to-end, and the real provider wiring (fake SDKs)."""

import json

from renocore.schemas.entities import (
    Assignment,
    LabelAnswer,
    PhotoCheckResult,
    Region,
)
from renocore.vision import (
    FakeProvider,
    RealProvider,
    apply_labels,
    get_provider,
    photo_verdict,
    proposed_regions,
    render_design,
)
from renocore.vision.memo import FileCache
from renocore.vision.stub import photo_key
from tests.unit.vision.conftest import (
    FakeGeminiSDK,
    FakeJevSDK,
    image_response,
    make_gemini,
    make_jev,
    make_photo,
    png_bytes,
)


def test_get_provider(settings, recorder):
    assert isinstance(get_provider(settings), FakeProvider)
    real = get_provider(settings.model_copy(update={"ai_provider": "real"}), recorder)
    assert isinstance(real, RealProvider)
    assert real.cache.root == settings.storage_root / "ai_cache"


async def test_fake_provider_end_to_end(settings, recorder, materials):
    provider = get_provider(settings, recorder)
    photo = make_photo(800, 600)
    checks = PhotoCheckResult(width=800, height=600, sharpness=300, brightness=0.5)

    answers = await provider.whole_photo(photo)
    assert photo_verdict(checks, answers).status == "pass"
    assert answers.main_door is not None and answers.door_visible >= 0.7

    candidates = await provider.segment(photo)
    labels = [c.label_hint for c in candidates]
    assert labels.count("wall") == 2 and labels.count("window") == 3
    assert {"parapet", "door", "pillar", "balcony", "railing"} <= set(labels)
    assert all(0 <= x <= 800 and 0 <= y <= 600 for c in candidates for x, y in c.polygon)

    regions = [
        Region(id=f"r{i}", label=c.label_hint, polygon=c.polygon) for i, c in enumerate(candidates)
    ]
    label_answers = await provider.label_regions(photo, regions)
    final = apply_labels(regions, label_answers, settings.region_confidence_threshold)
    flagged = [r for r in final if r.needs_check]
    assert len(flagged) == 1 and flagged[0].label == "pillar"
    assert proposed_regions(answers, final, 800, 600) == []

    advice = await provider.material_advice(photo, final, materials)
    wall_advice = next(a for a in advice if a.region_id == "r0")
    assert wall_advice.recommended == ["paint", "stone"]
    assert "lime" in wall_advice.not_ideal
    assert all(a.region_id not in {"r3", "r4", "r5", "r6"} for a in advice)  # openings skipped

    outcome = await render_design(
        provider,
        photo,
        final,
        [
            Assignment(region_id="r0", material_id="stone"),
            Assignment(region_id="r10", material_id="glass"),
        ],
        materials,
        None,
        settings.render_max_auto_regenerate,
        settings.render_qa_threshold,
    )
    assert outcome.attempts == 1 and outcome.qa.passed
    assert outcome.image.size == (800, 600)
    assert {c.step for c in recorder.calls} == {"C1", "C2", "C3", "C4", "C5", "C6"}
    assert all(c.provider == "fake" for c in recorder.calls)


async def test_fake_provider_replays_fixtures(tmp_path):
    photo = make_photo(100, 80)
    key = photo_key(photo)
    (tmp_path / f"{key}.C3.json").write_text(
        json.dumps({"x": {"label": "gate", "confidence": 0.77, "probabilities": {}}})
    )
    (tmp_path / f"{key}.C1.json").write_text(
        json.dumps(
            {
                "is_residential_exterior": 0.2,
                "building_type": {"choice": "commercial"},
                "view_angle": {"choice": "side"},
                "facade_obstructed": 0.1,
                "usability": 0.5,
                "door_visible": 0.1,
                "floors": {"choice": "1"},
                "railing_visible": 0.0,
                "gate_visible": 0.0,
            }
        )
    )
    (tmp_path / f"{key}.C2.json").write_text(
        json.dumps(
            [
                {
                    "label_hint": "wall",
                    "polygon": [[0, 0], [10, 0], [10, 10]],
                    "box": {"x0": 0, "y0": 0, "x1": 10, "y1": 10},
                }
            ]
        )
    )
    (tmp_path / f"{key}.C4.json").write_text(
        json.dumps([{"region_id": "x", "recommended": ["paint"]}])
    )
    fake = FakeProvider(fixtures_dir=tmp_path)
    assert (await fake.label_regions(photo, [])) == {
        "x": LabelAnswer(label="gate", confidence=0.77)
    }
    assert (await fake.whole_photo(photo)).building_type.choice == "commercial"
    assert len(await fake.segment(photo)) == 1
    assert (await fake.material_advice(photo, [], {}))[0].recommended == ["paint"]
    # an unrelated photo falls back to synthetic answers
    other = await fake.label_regions(make_photo(50, 50), [])
    assert other == {}


async def test_real_provider_wiring(settings, tmp_path, recorder, materials):
    labelmap = image_response(png_bytes(40, 30, (250, 5, 5)))  # label map: all wall
    gemini_sdk = FakeGeminiSDK([labelmap, image_response(png_bytes(40, 30))])
    jev_sdk = FakeJevSDK()
    cache = FileCache(tmp_path / "cache")
    provider = RealProvider(
        settings,
        recorder,
        jev=make_jev(jev_sdk, recorder, cache),
        gemini=make_gemini(gemini_sdk, recorder),
        cache=cache,
    )
    photo = make_photo(400, 300)
    assert (await provider.whole_photo(photo)).is_residential_exterior == 0.9
    cands = await provider.segment(photo)
    assert cands[0].label_hint == "wall"
    regions = [Region(id="w", label="wall", polygon=cands[0].polygon)]
    assert (await provider.label_regions(photo, regions))["w"].label == "wall"
    assert (await provider.material_advice(photo, regions, materials))[0].region_id == "w"
    outcome = await render_design(
        provider,
        photo,
        regions,
        [Assignment(region_id="w", material_id="stone")],
        materials,
        None,
        2,
        0.6,
    )
    assert outcome.qa.passed and outcome.attempts == 1
    assert len(gemini_sdk.calls) == 2 and len(jev_sdk.calls) == 4
    await provider.aclose()
