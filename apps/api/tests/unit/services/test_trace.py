from app.domain.models import Material
from app.services.trace import describe, needs_attention, starts_run

PAINT = Material(
    id="paint",
    name="Premium exterior emulsion",
    category="paint",
    description="paint",
    applicable_labels=["wall"],
    pricing_unit="litre",
    measure_basis="area",
    coverage_sqft_per_unit=110,
    wastage_pct=5,
    material_rate=420,
    labour_rate=14,
    swatch="paint.png",
    weather_resistance="high",
    durability="6-8 years",
    maintenance="Wash yearly.",
)
CAT = {"paint": PAINT}


def run(step, output, ok=True):
    return describe(step, output, ok, CAT, 0.6, 0.6)


def test_titles_and_stages_have_no_internal_codes():
    for step in ("C1", "C2", "C3", "C4", "C5", "C6"):
        stage, title, summary = run(step, {})
        assert stage in {"photo", "materials", "look"}
        assert "C" + step[1] not in title and title[0].isupper()
        assert summary


def test_photo_check_summary():
    out = {
        "building_type": {"choice": "independent_house"},
        "floors": {"choice": "2"},
        "view_angle": {"choice": "straight_on"},
        "door_visible": {"noul": 0.81},
    }
    assert run("C1", out)[2] == (
        "Looks like an independent house with 2 floors, photographed from the front. "
        "The main door is visible."
    )


def test_parts_found_summary():
    out = {"counts": {"wall": 7, "window": 1, "door": 1, "gate": 0}}
    assert run("C2", out)[2] == "Found 7 wall areas, 1 window and 1 door."


def test_labels_summary_counts_please_check():
    out = {
        "region_a": {"choice": "wall", "confidence": 0.9},
        "region_b": {"choice": "pillar", "confidence": 0.45},
    }
    assert run("C3", out)[2] == "Confirmed 2 parts; 1 marked “Please check” for you."


def test_materials_summary_names_the_top_pick():
    out = {"fit_wall": {"choice": "paint"}, "exposed_wall": {"noul": 0.8}}
    assert run("C4", out)[2] == "Top pick: Premium exterior emulsion for the main wall."


def test_render_and_check_summaries():
    assert run("C5", {"attempt": 0})[2] == "Applied your chosen materials to the photo."
    assert "attempt 2" in run("C5", {"attempt": 1})[2]
    good = {"openings_preserved": {"noul": 0.9}, "zone_red": {"noul": 0.8}}
    assert run("C6", good)[2] == "Everything looked right."
    bad = {"openings_preserved": {"noul": 0.4}, "zone_red": {"noul": 0.3}}
    assert run("C6", bad)[2] == (
        "Windows or doors may look different and 1 chosen material was not clearly visible."
    )


def test_failed_call_summary():
    stage, title, summary = run("C4", None, ok=False)
    assert (stage, title) == ("materials", "Suggested materials")
    assert "tried again" in summary


def test_attention_flags():
    assert needs_attention("C6", "Windows or doors may look different.")
    assert not needs_attention("C6", "Everything looked right.")
    assert needs_attention("C3", "Confirmed 2 parts; 1 marked “Please check” for you.")
    assert not needs_attention("C3", "Confirmed 2 parts.")
    assert not needs_attention("C2", "Found 1 door.")


def test_starts_run_only_on_first_render_attempt():
    assert starts_run("C5", {"attempt": 0})
    assert not starts_run("C5", {"attempt": 1})
    assert not starts_run("C6", {"attempt": 0})
    assert not starts_run("C5", None)
