"""render_design loop: zones, zone map, composite, QA and auto-regeneration."""

import pytest

from app import imaging
from app.ai import render_design
from app.ai.rules import OPENINGS_FIX
from app.ai.steps.render import ZONE_PALETTE, build_zones
from app.domain.models import Assignment, QAResult
from tests.unit.ai.conftest import make_photo, make_region


def qa(openings=0.9, structure=0.9, zone=0.9) -> QAResult:
    return QAResult(
        openings_preserved=openings,
        structure_preserved=structure,
        zones={"red": zone, "blue": zone},
        passed=True,
    )


class ScriptedProvider:
    def __init__(self, results: list[QAResult], with_attempt: bool = True) -> None:
        self.results = list(results)
        self.generate_calls: list[dict] = []
        self.check_calls = 0
        if not with_attempt:
            self.generate_redesign = self._generate_no_attempt  # type: ignore[method-assign]

    async def generate_redesign(
        self, photo, zone_map, zones, materials, user_note=None, fix_notes=None, attempt=0
    ):
        self.generate_calls.append(
            {
                "zones": zones,
                "materials": materials,
                "note": user_note,
                "fix_notes": fix_notes,
                "attempt": attempt,
            }
        )
        return make_photo(photo.width // 2, photo.height // 2, (0, 255, 0))

    async def _generate_no_attempt(
        self, photo, zone_map, zones, materials, user_note=None, fix_notes=None
    ):
        self.generate_calls.append({"fix_notes": fix_notes, "attempt": None})
        return make_photo(photo.width, photo.height, (0, 255, 0))

    async def check_render(self, original, result, zone_map, zones, materials):
        self.check_calls += 1
        return self.results.pop(0)


@pytest.fixture
def scene():
    regions = [
        make_region("w1", "wall", (0, 0, 200, 150)),
        make_region("w2", "wall", (200, 0, 400, 150)),
        make_region("p1", "pillar", (0, 150, 40, 300)),
        make_region("win", "window", (50, 50, 100, 100)),
    ]
    assignments = [
        Assignment(region_id="w1", material_id="stone"),
        Assignment(region_id="w2", material_id="stone"),
        Assignment(region_id="p1", material_id="paint", color="#AA0000"),
        Assignment(region_id="win", material_id="paint"),  # openings are never redesigned
        Assignment(region_id="ghost", material_id="paint"),
        Assignment(region_id="w1", material_id="unknown"),
    ]
    return make_photo(400, 300), regions, assignments


async def run(provider, scene, materials, max_regen=2):
    photo, regions, assignments = scene
    return await render_design(
        provider, photo, regions, assignments, materials, "warm tones", max_regen, 0.6
    )


async def test_passes_first_time(scene, materials, monkeypatch):
    seen = {}

    def composite(original, generated, include, exclude, feather_px=3):
        seen["include"], seen["exclude"] = include, exclude
        return generated.resize(original.size)

    monkeypatch.setattr(imaging, "composite", composite)
    provider = ScriptedProvider([qa()])
    out = await run(provider, scene, materials)
    assert out.attempts == 1 and out.qa.passed and out.qa.failed_checks == []
    assert out.image.size == (400, 300)
    assert out.zone_map.size == (400, 300)
    assert out.zone_map.getpixel((10, 10)) == (230, 25, 45)  # red zone painted
    call = provider.generate_calls[0]
    assert call["note"] == "warm tones" and call["fix_notes"] is None and call["attempt"] == 0
    assert [(z.color_name, z.material_id, z.region_ids) for z in call["zones"]] == [
        ("red", "stone", ["w1", "w2"]),
        ("blue", "paint@aa0000", ["p1"]),
    ]
    assert call["materials"]["paint@aa0000"].default_color == "#aa0000"
    assert len(seen["include"]) == 3 and seen["exclude"] == [scene[1][3].polygon]


async def test_fails_then_passes(scene, materials):
    provider = ScriptedProvider([qa(openings=0.2), qa()])
    out = await run(provider, scene, materials)
    assert out.attempts == 2 and out.qa.passed
    assert provider.generate_calls[1]["fix_notes"] == [OPENINGS_FIX]
    assert provider.generate_calls[1]["attempt"] == 1


async def test_never_passes_returns_best_attempt(scene, materials):
    provider = ScriptedProvider([qa(zone=0.1), qa(zone=0.5), qa(structure=0.3)])
    out = await run(provider, scene, materials)
    assert out.attempts == 3 and provider.check_calls == 3
    assert not out.qa.passed
    assert out.qa.zones["red"] == 0.5  # attempt 2 had the highest minimum score
    assert out.qa.failed_checks == [
        "The area shown in red must be natural stone cladding.",
        "The area shown in blue must be beige texture paint.",
    ]
    assert provider.generate_calls[2]["fix_notes"] == out.qa.failed_checks


async def test_threshold_is_applied_by_render_design(scene, materials):
    provider = ScriptedProvider([qa(zone=0.65)])
    photo, regions, assignments = scene
    out = await render_design(provider, photo, regions, assignments, materials, None, 0, 0.7)
    assert out.attempts == 1 and not out.qa.passed


async def test_provider_without_attempt_kwarg(scene, materials):
    provider = ScriptedProvider([qa(openings=0.1), qa()], with_attempt=False)
    out = await run(provider, scene, materials, max_regen=1)
    assert out.attempts == 2 and provider.generate_calls[0]["attempt"] is None


async def test_cache_salt_is_passed_through(scene, materials):
    seen = []

    class Salted(ScriptedProvider):
        async def generate_redesign(
            self,
            photo,
            zone_map,
            zones,
            materials,
            user_note=None,
            fix_notes=None,
            attempt=0,
            cache_salt=None,
        ):
            seen.append((attempt, cache_salt))
            return photo

    photo, regions, assignments = scene
    await render_design(
        Salted([qa(openings=0.1), qa()]),
        photo,
        regions,
        assignments,
        materials,
        None,
        2,
        0.6,
        cache_salt="render-7",
    )
    assert seen == [(0, "render-7"), (1, "render-7")]


async def test_no_zones_is_an_error(materials):
    with pytest.raises(ValueError, match="at least one part"):
        await render_design(
            ScriptedProvider([]),
            make_photo(),
            [make_region("w", "wall")],
            [],
            materials,
            None,
            2,
            0.6,
        )


def test_zone_colours_distinct_and_capped(materials):
    regions = [make_region(f"r{i}", "wall") for i in range(13)]
    colours = [f"#{i:02x}0000" for i in range(13)]
    assignments = [
        Assignment(region_id=f"r{i}", material_id="paint", color=colours[i]) for i in range(12)
    ]
    zones, _ = build_zones(regions, assignments, materials)
    assert len({z.color_name for z in zones}) == 12 == len(ZONE_PALETTE)
    assignments.append(Assignment(region_id="r12", material_id="paint", color=colours[12]))
    with pytest.raises(ValueError, match="At most 12"):
        build_zones(regions, assignments, materials)


def test_default_colour_is_not_a_variant(materials):
    zones, mats = build_zones(
        [make_region("w", "wall")],
        [Assignment(region_id="w", material_id="paint", color="#EEDDCC")],
        materials,
    )
    assert zones[0].material_id == "paint" and mats == materials
