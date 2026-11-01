"""Buying the cheapest mix of pack sizes (e.g. 1, 4, 10 and 20 L paint cans)."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from renocore.costing import best_packs
from renocore.costing.takeoff import material_quantity
from tests.unit.costing.helpers import paint_material

CANS = [1, 4, 10, 20]


@pytest.mark.parametrize(
    ("required", "mix"),
    [
        (3.15, [(4, 1)]),  # not a 10 L can
        (4.85, [(4, 1), (1, 1)]),
        (8, [(4, 2)]),
        (10, [(10, 1)]),
        (23, [(20, 1), (1, 3)]),
        (0.2, [(1, 1)]),
        (39.9, [(20, 2)]),
    ],
)
def test_least_paint_bought(required: float, mix: list[tuple[float, int]]) -> None:
    assert best_packs(required, CANS) == mix


def test_single_size_and_nothing_needed() -> None:
    assert best_packs(9.47, [25]) == [(25, 1)]
    assert best_packs(50.1, [25]) == [(25, 3)]
    assert best_packs(0, CANS) == []
    assert best_packs(1e-12, CANS) == [(1, 1)]  # any need at all buys one can


@given(st.floats(min_value=0.01, max_value=500))
def test_mix_covers_the_need_with_less_than_one_small_can_spare(required: float) -> None:
    mix = best_packs(required, CANS)
    bought = sum(size * n for size, n in mix)
    assert bought >= required * (1 - 1e-9)
    assert bought - required < 1 + 1e-9  # 1 L cans exist, so never more than 1 L over


def test_paint_line_uses_the_mix() -> None:
    m = paint_material(pack_size=10, pack_sizes=[1, 4, 20])  # 100 sqft/L, 2 coats
    q = material_quantity(m, 150, "sqft")  # needs 3 L
    assert (q.purchase, q.packs, q.pack_size, q.pack_mix) == (3, 3, 1, [(1, 3)])
    assert q.derivation[0].endswith("→ 3 × 1 L cans")
    q = material_quantity(m, 270, "sqft")  # needs 5.4 L
    assert (q.purchase, q.packs, q.pack_size) == (6, 3, None)
    assert q.derivation[0].endswith("→ 1 × 4 L + 2 × 1 L cans")


def test_without_extra_sizes_nothing_changes() -> None:
    q = material_quantity(paint_material(pack_size=4), 250, "sqft")  # needs 5 L
    assert (q.purchase, q.packs, q.pack_size) == (8, 2, 4)
    assert q.derivation[0].endswith("→ 2 × 4 L cans")
