from __future__ import annotations

import json

import pytest
from PIL import Image
from pydantic import ValidationError

from renocore.costing import (
    DEFAULT_CATALOGUE_PATH,
    DEFAULT_SWATCH_DIR,
    check_material,
    load_catalogue,
    missing_swatches,
)
from renocore.schemas.entities import LABELS

from .helpers import make_material


@pytest.fixture(scope="module")
def cat():
    return load_catalogue(DEFAULT_CATALOGUE_PATH)


def test_seed_catalogue_loads(cat):
    assert 15 <= len(cat) <= 35
    assert {m.category for m in cat.values()} == {
        "paint",
        "texture",
        "cladding",
        "tiles",
        "panel",
        "railing",
        "gate",
    }
    assert {m.pricing_unit for m in cat.values()} == {
        "litre",
        "kg",
        "piece",
        "sqft",
        "sheet",
        "rft",
    }
    for m in cat.values():
        assert set(m.applicable_labels) <= set(LABELS)
        assert not set(m.applicable_labels) & {"window", "door"}
        assert m.swatch == f"{m.id}.png"
        assert m.material_rate > 0 and m.labour_rate > 0


def test_seed_label_rules(cat):
    for m in cat.values():
        if m.category == "railing":
            assert m.applicable_labels == ["railing"] and m.measure_basis == "length"
        if m.category == "gate":
            assert m.applicable_labels == ["gate"]
        if m.category in ("paint", "texture"):
            assert set(m.applicable_labels) == {
                "wall",
                "parapet",
                "pillar",
                "balcony",
                "roof_edge",
                "canopy",
                "compound_wall",
            }
        if m.category == "tiles":
            assert m.companions and m.companions[0].kind == "adhesive"
        if m.category == "paint":
            assert m.companions and m.companions[0].kind == "primer" and m.colorable


def test_all_swatches_exist_and_are_512(cat):
    assert missing_swatches(cat, DEFAULT_SWATCH_DIR) == []
    for m in cat.values():
        with Image.open(DEFAULT_SWATCH_DIR / m.swatch) as im:
            assert im.size == (512, 512)


def test_missing_swatch_reported(cat, tmp_path):
    assert missing_swatches(cat, tmp_path) == list(cat)


def _write(tmp_path, items):
    p = tmp_path / "materials.json"
    p.write_text(json.dumps(items), encoding="utf-8")
    return p


def test_duplicate_ids_rejected(tmp_path):
    m = make_material().model_dump(mode="json")
    with pytest.raises(ValueError, match="duplicate"):
        load_catalogue(_write(tmp_path, [m, m]))


def test_schema_errors_rejected(tmp_path):
    m = make_material().model_dump(mode="json")
    del m["material_rate"]
    with pytest.raises(ValidationError):
        load_catalogue(_write(tmp_path, [m]))


@pytest.mark.parametrize(
    "kw",
    [
        {"pricing_unit": "litre"},
        {"pricing_unit": "kg", "coverage_sqft_per_unit": 0},
        {"pricing_unit": "piece"},
        {"pricing_unit": "sheet"},
        {"pricing_unit": "rft"},
        {"measure_basis": "length"},
        {"coats": 0},
        {"wastage_pct": -1},
        {"pack_size": 0},
        {"pieces_per_box": 0},
        {"colorable": True},
        {"applicable_labels": []},
        {
            "companions": [
                {
                    "kind": "primer",
                    "name": "P",
                    "unit": "litre",
                    "quantity_per_sqft": 0.01,
                    "pack_size": 0,
                    "rate": 1,
                }
            ]
        },
    ],
)
def test_unit_rules(kw, tmp_path):
    with pytest.raises(ValueError):
        check_material(make_material(**kw))
    with pytest.raises(ValueError):
        load_catalogue(_write(tmp_path, [make_material(**kw).model_dump(mode="json")]))


def test_valid_custom_material_passes():
    check_material(make_material(pricing_unit="rft", measure_basis="length"))
