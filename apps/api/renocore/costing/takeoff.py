"""Quantity rules per pricing unit (estimation.md section 4)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from renocore.schemas.entities import Companion, Material

_EPS = 1e-9

PURCHASE_UNITS: dict[str, str] = {
    "litre": "L",
    "kg": "kg",
    "piece": "pieces",
    "sheet": "sheets",
    "sqft": "sqft",
    "rft": "rft",
}
_PACK_WORDS: dict[str, tuple[str, str]] = {
    "litre": ("can", "cans"),
    "kg": ("bag", "bags"),
    "piece": ("box", "boxes"),
}


def fmt(x: float, dp: int = 1) -> str:
    """Number for humans: thousands separators, up to ``dp`` decimals, no trailing zeros."""
    s = f"{x:,.{dp}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def money(x: float) -> str:
    return f"₹{x:,.0f}"


def ceil_safe(x: float) -> int:
    """Ceiling that tolerates relative floating-point noise (8.000000001 -> 8)."""
    if x <= 0:
        return 0
    return math.ceil(x * (1 - _EPS))


def with_wastage(measured: float, wastage_pct: float) -> float:
    """with_wastage = measured x (1 + wastage%)."""
    return measured * (1 + wastage_pct / 100)


def round_to_packs(required: float, pack_size: float | None) -> tuple[int | None, float]:
    """(packs, purchase quantity). Without a pack size, round up to whole units."""
    if pack_size is None or pack_size <= 0:
        return None, float(ceil_safe(required))
    packs = ceil_safe(required / pack_size)
    return packs, packs * pack_size


def best_packs(required: float, sizes: list[float]) -> list[tuple[float, int]]:
    """Cheapest mix of pack sizes covering ``required``: least quantity bought, then fewest
    packs. Price is per unit, so the least quantity is the lowest cost. Largest size first."""
    sizes = sorted({s for s in sizes if s > 0}, reverse=True)
    if required <= 0 or not sizes:
        return []
    best: tuple[float, int, list[tuple[float, int]]] | None = None

    def search(i: int, left: float, picked: list[tuple[float, int]]) -> None:
        nonlocal best
        size = sizes[i]
        if i == len(sizes) - 1:  # smallest size covers whatever is left
            options = [ceil_safe(left / size)]
        else:  # either stop short of `left` with this size, or cover it fully
            options = sorted({int(left // size), ceil_safe(left / size)})
        for n in options:
            mix = picked + ([(size, n)] if n else [])
            rest = left - n * size
            if rest <= _EPS * required or i == len(sizes) - 1:
                bought = sum(sz * k for sz, k in mix)
                key = (round(bought, 6), sum(k for _, k in mix))
                if best is None or key < best[:2]:
                    best = (*key, mix)
            else:
                search(i + 1, rest, mix)

    search(0, required, [])
    assert best is not None
    return best[2]


def _packs_word(unit: str, n: int) -> str:
    one, many = _PACK_WORDS.get(unit, ("pack", "packs"))
    return one if n == 1 else many


@dataclass
class Quantity:
    """Purchase quantity for the main material of a line."""

    required: float
    purchase: float
    purchase_unit: str
    packs: int | None = None
    pack_size: float | None = None
    derivation: list[str] = field(default_factory=list)
    pack_mix: list[tuple[float, int]] = field(default_factory=list)


def material_quantity(material: Material, ww: float, measured_unit: str) -> Quantity:
    """Apply the pricing-unit rule to a quantity that already includes wastage."""
    unit = material.pricing_unit
    pu = PURCHASE_UNITS[unit]
    mu = "sq ft" if measured_unit == "sqft" else "running ft"
    if unit in ("litre", "kg"):
        cov = _require(material.coverage_sqft_per_unit, material, "coverage_sqft_per_unit")
        coats = material.coats
        required = ww * coats / cov
        per = "sq ft per litre" if unit == "litre" else "sq ft per kg"
        coats_txt = f" × {coats} coats" if coats != 1 else ""
        step = f"{fmt(ww)} {mu}{coats_txt} ÷ {fmt(cov)} {per} = {fmt(required, 2)} {pu}"
        sizes = [material.pack_size, *material.pack_sizes] if material.pack_size else []
        if not sizes or required <= 0:
            packs, purchase = round_to_packs(required, material.pack_size)
            if packs is not None and material.pack_size is not None:
                word = _packs_word(unit, packs)
                step += f" → {packs} × {fmt(material.pack_size)} {pu} {word}"
            else:
                step += f" → {fmt(purchase)} {pu}"
            return Quantity(required, purchase, pu, packs, material.pack_size, [step])
        mix = best_packs(required, sizes)
        purchase = sum(size * n for size, n in mix)
        packs = sum(n for _, n in mix)
        step += " → " + " + ".join(f"{n} × {fmt(size)} {pu}" for size, n in mix)
        step += f" {_packs_word(unit, packs)}"
        single = mix[0][0] if len(mix) == 1 else None
        return Quantity(required, purchase, pu, packs, single, [step], pack_mix=mix)
    if unit == "piece":
        piece = _require(material.piece_area_sqft, material, "piece_area_sqft")
        required = ww / piece
        pieces = ceil_safe(required)
        step = f"{fmt(ww)} {mu} ÷ {fmt(piece, 2)} sq ft per piece = {pieces} pieces"
        ppb = material.pieces_per_box
        if ppb:
            boxes = ceil_safe(pieces / ppb)
            purchase = float(boxes * ppb)
            step += f" → {boxes} {_packs_word(unit, boxes)} of {ppb} = {fmt(purchase)} pieces"
            return Quantity(required, purchase, pu, boxes, float(ppb), [step])
        return Quantity(required, float(pieces), pu, None, None, [step])
    if unit == "sheet":
        sheet = _require(material.piece_area_sqft, material, "piece_area_sqft")
        required = ww / sheet
        sheets = ceil_safe(required)
        step = f"{fmt(ww)} {mu} ÷ {fmt(sheet, 2)} sq ft per sheet = {sheets} sheets"
        return Quantity(required, float(sheets), pu, None, None, [step])
    # sqft / rft: buy whole units
    purchase = float(ceil_safe(ww))
    dp = 2 if unit == "rft" else 1
    step = f"{fmt(ww, dp)} {mu} rounded up to {fmt(purchase)} {mu}"
    return Quantity(ww, purchase, pu, None, None, [step])


def companion_quantity(companion: Companion, ww: float) -> tuple[float, int, float]:
    """(required, packs, purchase) for an auto-added primer/adhesive."""
    required = ww * companion.quantity_per_sqft
    packs, purchase = round_to_packs(required, companion.pack_size)
    return required, packs or 0, purchase


def _require(value: float | None, material: Material, name: str) -> float:
    if value is None or value <= 0:
        raise ValueError(f"material {material.id!r} needs a positive {name}")
    return value
