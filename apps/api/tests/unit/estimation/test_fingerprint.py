from __future__ import annotations

import hashlib

import pytest

from app.domain.models import Assignment, Extras, RateOverride
from app.estimation import canonical_json, compute_estimate, estimate_fingerprint, fingerprint

from .helpers import box_region, make_material, scale_of
from .test_estimate import inputs


def test_fingerprint_is_sha256_of_canonical_json():
    assert canonical_json({"b": 1, "a": [1, 2]}) == '[{"a":[1,2],"b":1}]'
    assert fingerprint({"b": 1, "a": 2}) == hashlib.sha256(b'[{"a":2,"b":1}]').hexdigest()
    assert fingerprint({"a": 2, "b": 1}) == fingerprint({"b": 1, "a": 2})
    assert fingerprint(1, 2) != fingerprint(2, 1)


def test_fingerprint_pydantic_and_tuples():
    m = make_material()
    assert fingerprint(m) == fingerprint(m.model_dump(mode="json"))
    assert fingerprint((1, 2)) == fingerprint([1, 2])
    assert fingerprint({1: "x"}) == fingerprint({"1": "x"})


def test_same_inputs_same_hash():
    assert compute_estimate(inputs()).fingerprint == compute_estimate(inputs()).fingerprint


def test_order_of_regions_and_assignments_does_not_matter():
    a = inputs()
    b = inputs(regions=list(reversed(a.regions)), assignments=list(reversed(a.assignments)))
    assert estimate_fingerprint(a) == estimate_fingerprint(b)


def test_unused_catalogue_entries_do_not_matter():
    a = inputs()
    mats = dict(a.materials)
    mats["unused"] = make_material(id="unused")
    assert estimate_fingerprint(a) == estimate_fingerprint(inputs(materials=mats))


@pytest.mark.parametrize(
    "change",
    [
        lambda i: {"regions": [*i.regions, box_region("x", "wall", 0, 0, 5, 5)]},
        lambda i: {"regions": [box_region("wall", "wall", 0, 0, 1001, 500), *i.regions[1:]]},
        lambda i: {"scale": scale_of(0.021)},
        lambda i: {"assignments": i.assignments[:-1]},
        lambda i: {
            "assignments": [
                *i.assignments[:-1],
                Assignment(region_id="gate", material_id="gate", color="#000000"),
            ]
        },
        lambda i: {
            "materials": {
                **i.materials,
                "gate": i.materials["gate"].model_copy(update={"material_rate": 401}),
            }
        },
        lambda i: {"overrides": [RateOverride(material_id="gate", labour_rate=1)]},
        lambda i: {"extras": Extras(tax_pct=12)},
        lambda i: {"floors": 2},
        lambda i: {"scale_confirmed": False},
    ],
)
def test_any_change_changes_hash(change):
    base = inputs()
    assert estimate_fingerprint(inputs(**change(base))) != estimate_fingerprint(base)
