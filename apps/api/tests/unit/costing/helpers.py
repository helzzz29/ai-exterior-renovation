"""Shared builders for estimation tests."""

from __future__ import annotations

import math
from typing import Any

from renocore.schemas.entities import (
    Companion,
    Confidence,
    Material,
    Region,
    ScaleMethod,
    ScaleResult,
)


def rect(x0: float, y0: float, x1: float, y1: float) -> list[tuple[float, float]]:
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def region(rid: str, label: str, poly: list[tuple[float, float]]) -> Region:
    return Region(id=rid, label=label, polygon=poly)  # type: ignore[arg-type]


def box_region(rid: str, label: str, x0: float, y0: float, x1: float, y1: float) -> Region:
    return region(rid, label, rect(x0, y0, x1, y1))


def scale_of(
    ft_per_px: float, confidence: Confidence = Confidence.high, method=ScaleMethod.user_measurement
) -> ScaleResult:
    return ScaleResult(
        ft_per_px=ft_per_px,
        method=method,
        confidence=confidence,
        explanation="We used the measurement you gave us.",
        needs_measurement=confidence == Confidence.low,
    )


def make_material(**kw: Any) -> Material:
    base: dict[str, Any] = {
        "id": "m",
        "name": "Test material",
        "category": "paint",
        "description": "test",
        "applicable_labels": ["wall"],
        "pricing_unit": "sqft",
        "measure_basis": "area",
        "wastage_pct": 0,
        "material_rate": 10,
        "labour_rate": 1,
        "swatch": "m.png",
        "weather_resistance": "medium",
        "durability": "5 years",
        "maintenance": "none",
    }
    base.update(kw)
    return Material(**base)


def paint_material(**kw: Any) -> Material:
    args: dict[str, Any] = {
        "id": "paint",
        "pricing_unit": "litre",
        "coverage_sqft_per_unit": 100,
        "coats": 2,
        "pack_size": 4,
        "wastage_pct": 0,
        "material_rate": 400,
        "labour_rate": 10,
        "companions": [
            Companion(
                kind="primer",
                name="Exterior primer",
                unit="litre",
                quantity_per_sqft=0.01,
                pack_size=4,
                rate=250,
            )
        ],
    }
    args.update(kw)
    return make_material(**args)


def trapezoid_wall(net_px: float, fs: float, width: float, hole_px: float = 0.0):
    """A right-trapezoid wall (vertical sides, flat bottom, sloping top) whose gross area is
    ``net_px + hole_px`` and whose foreshortening factor is ``fs``. Bottom-left at (0, 2000).
    """
    from renocore.costing import foreshortening

    s = 2 * (net_px + hole_px) / width  # a + b

    def poly(a: float) -> list[tuple[float, float]]:
        b = s - a
        return [(0, 2000), (width, 2000), (width, 2000 - b), (0, 2000 - a)]

    lo, hi = s / 4, s / 2 - 1e-9  # fs decreases as a -> s/2
    for _ in range(200):
        mid = (lo + hi) / 2
        if foreshortening(poly(mid)) > fs:
            lo = mid
        else:
            hi = mid
    pts = poly((lo + hi) / 2)
    assert math.isclose(foreshortening(pts), fs, rel_tol=1e-9)
    return pts
