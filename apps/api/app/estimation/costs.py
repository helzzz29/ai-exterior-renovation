"""Cost, extras and the full estimate (estimation.md sections 5 and 6).

Money convention: the worked example in estimation.md shows every amount to the whole
rupee and adds the rounded amounts (lines -> scaffolding -> contingency -> tax). We do the
same, so that every figure the homeowner sees adds up exactly. Rounding is half-up.
Quantities (areas, litres, ...) are kept at full precision.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.domain.models import (
    OPENING_LABELS,
    Companion,
    CompanionLine,
    Confidence,
    Estimate,
    EstimateInputs,
    Extras,
    Label,
    LineItem,
    Material,
    PackCount,
    RateOverride,
    ScaleMethod,
    SurfaceMeasure,
)

from .fingerprint import estimate_fingerprint
from .geometry import measure_surfaces
from .quantities import companion_quantity, fmt, material_quantity, money, with_wastage
from .scale import DOOR_HEIGHT_FT, STOREY_HEIGHT_FT, WINDOW_HEIGHT_FT

_UNIT_TEXT = {"sqft": "sq ft", "rft": "running ft"}

RANGE_PCT: dict[Confidence, float] = {
    Confidence.high: 10.0,
    Confidence.medium: 20.0,
    Confidence.low: 35.0,
}


def round_money(x: float, step: float = 1.0) -> float:
    """Half-up rounding of an amount to a multiple of ``step`` rupees."""
    q = (Decimal(repr(x)) / Decimal(repr(step))).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return float(q * Decimal(repr(step)))


def _companion_line(
    companion: Companion, ww: float, measured_unit: str
) -> tuple[CompanionLine, list[str]]:
    required, packs, purchase = companion_quantity(companion, ww)
    cost = round_money(purchase * companion.rate)
    unit = "L" if companion.unit == "litre" else "kg"
    word = ("can" if packs == 1 else "cans") if unit == "L" else ("bag" if packs == 1 else "bags")
    mu = "sq ft" if measured_unit == "sqft" else "running ft"
    qps = companion.quantity_per_sqft
    if 0 < qps < 0.1:
        rate_txt = f"÷ {fmt(1 / qps)} {mu} per {companion.unit}"
    else:
        rate_txt = f"× {fmt(qps, 3)} {unit} per {mu}"
    steps = [
        f"{companion.name}: {fmt(ww)} {mu} {rate_txt} = {fmt(required, 2)} {unit}"
        f" → {packs} × {fmt(companion.pack_size)} {unit} {word}",
        f"{companion.name}: {fmt(purchase)} {unit} × {money(companion.rate)} = {money(cost)}",
    ]
    line = CompanionLine(
        name=companion.name,
        quantity=required,
        unit=unit,
        packs=packs,
        purchase_quantity=purchase,
        rate=companion.rate,
        cost=cost,
    )
    return line, steps


def price_line(
    material: Material,
    label: Label,
    region_ids: list[str],
    measured: float,
    override: RateOverride | None = None,
) -> LineItem:
    """Quantity and cost for one material on one surface type (regions already summed)."""
    measured_unit = "rft" if material.measure_basis == "length" else "sqft"
    mu = "sq ft" if measured_unit == "sqft" else "running ft"
    what = "Area" if measured_unit == "sqft" else "Length"
    dp = 1 if measured_unit == "sqft" else 2
    ww = with_wastage(measured, material.wastage_pct)
    count = f" ({len(region_ids)} parts)" if len(region_ids) > 1 else ""
    derivation = [
        f"{what}{count} {fmt(measured, dp)} {mu} + {fmt(material.wastage_pct)}% wastage"
        f" = {fmt(ww, dp)} {mu}"
    ]
    qty = material_quantity(material, ww, measured_unit)
    derivation += qty.derivation

    material_rate = material.material_rate
    labour_rate = material.labour_rate
    overridden = False
    if override is not None:
        if override.material_rate is not None:
            material_rate, overridden = override.material_rate, True
        if override.labour_rate is not None:
            labour_rate, overridden = override.labour_rate, True

    material_cost = round_money(qty.purchase * material_rate)
    unit_text = _UNIT_TEXT.get(qty.purchase_unit, qty.purchase_unit)
    derivation.append(
        f"Material: {fmt(qty.purchase)} {unit_text} × {money(material_rate)}"
        f" = {money(material_cost)}"
    )
    companions: list[CompanionLine] = []
    for comp in material.companions:
        line, steps = _companion_line(comp, ww, measured_unit)
        companions.append(line)
        derivation += steps
    labour_cost = round_money(measured * labour_rate)
    derivation.append(
        f"Labour: {fmt(measured, dp)} {mu} × {money(labour_rate)} = {money(labour_cost)}"
    )
    parts = [material_cost, *(c.cost for c in companions), labour_cost]
    total = sum(parts)
    derivation.append(f"Total: {' + '.join(money(p) for p in parts)} = {money(total)}")
    return LineItem(
        material_id=material.id,
        material_name=material.name,
        category=material.category,
        label=label,
        region_ids=list(region_ids),
        measured_quantity=measured,
        measured_unit=measured_unit,
        wastage_pct=material.wastage_pct,
        with_wastage=ww,
        required_quantity=qty.required,
        purchase_quantity=qty.purchase,
        purchase_unit=qty.purchase_unit,
        packs=qty.packs,
        pack_size=qty.pack_size,
        pack_mix=[PackCount(size=size, count=n) for size, n in qty.pack_mix],
        material_rate=material_rate,
        material_cost=material_cost,
        companions=companions,
        labour_rate=labour_rate,
        labour_cost=labour_cost,
        total=total,
        rate_overridden=overridden,
        derivation=derivation,
    )


@dataclass
class Totals:
    lines_total: float
    scaffolding: float
    contingency: float
    tax: float
    grand_total: float
    range_pct: float
    range_low: float
    range_high: float


def apply_extras(
    lines_total: float,
    wall_area_sqft: float,
    floors: int,
    extras: Extras,
    confidence: Confidence,
) -> Totals:
    """Scaffolding, contingency, tax and the uncertainty range."""
    scaffolding = 0.0
    if floors >= extras.scaffolding_min_floors:
        scaffolding = round_money(wall_area_sqft * extras.scaffolding_rate_per_sqft)
    contingency = round_money(extras.contingency_pct / 100 * (lines_total + scaffolding))
    tax = round_money(extras.tax_pct / 100 * (lines_total + scaffolding + contingency))
    grand = lines_total + scaffolding + contingency + tax
    pct = RANGE_PCT[confidence]
    return Totals(
        lines_total=lines_total,
        scaffolding=scaffolding,
        contingency=contingency,
        tax=tax,
        grand_total=grand,
        range_pct=pct,
        range_low=round_money(grand * (1 - pct / 100), 100),
        range_high=round_money(grand * (1 + pct / 100), 100),
    )


# ---------------------------------------------------------------- full estimate


def build_lines(
    inputs: EstimateInputs, surfaces: list[SurfaceMeasure]
) -> tuple[list[LineItem], list[str]]:
    """Group assignments by (material, label), sum measured quantities, price each group.

    Returns the lines and the ids of assigned windows/doors that were skipped.
    """
    by_id = {s.region_id: s for s in surfaces}
    known = {r.id: r for r in inputs.regions}
    latest: dict[str, str] = {}  # region -> material (last assignment wins)
    for a in inputs.assignments:
        if a.region_id not in known:
            raise ValueError(f"assignment refers to unknown region {a.region_id!r}")
        if a.material_id not in inputs.materials:
            raise ValueError(f"assignment refers to unknown material {a.material_id!r}")
        latest.pop(a.region_id, None)
        latest[a.region_id] = a.material_id

    groups: dict[tuple[str, Label], list[str]] = {}
    skipped: list[str] = []
    for region_id, material_id in latest.items():
        if known[region_id].label in OPENING_LABELS:
            skipped.append(region_id)
            continue
        groups.setdefault((material_id, known[region_id].label), []).append(region_id)

    overrides: dict[str, RateOverride] = {}
    for o in inputs.overrides:
        overrides[o.material_id] = o

    lines: list[LineItem] = []
    for (material_id, label), region_ids in groups.items():
        material = inputs.materials[material_id]
        if material.measure_basis == "length":
            measured = sum(by_id[r].length_ft or 0.0 for r in region_ids)
        else:
            measured = sum(by_id[r].area_sqft for r in region_ids)
        lines.append(price_line(material, label, region_ids, measured, overrides.get(material_id)))
    return lines, skipped


def assumptions_for(
    inputs: EstimateInputs,
    surfaces: list[SurfaceMeasure],
    lines: list[LineItem],
    scaffolding_on: bool,
    skipped: list[str],
) -> list[str]:
    scale = inputs.scale
    out = [scale.explanation]
    if scale.method == ScaleMethod.door:
        out.append(f"A standard main door is taken as {DOOR_HEIGHT_FT:.0f} ft tall.")
    elif scale.method == ScaleMethod.windows:
        out.append(f"A standard window is taken as {WINDOW_HEIGHT_FT:.0f} ft tall.")
    elif scale.method == ScaleMethod.floors:
        out.append(f"Each floor is taken as about {STOREY_HEIGHT_FT:.0f} ft high.")
    if not inputs.scale_confirmed:
        out.append(
            "This is a first estimate. Please confirm the size of your house to finalise it."
        )
    out.append("Windows and doors are not painted or covered; their area is left out.")
    labels = {line.label for line in lines}
    if "pillar" in labels:
        out.append("Pillars are taken as square, with three sides showing (front and two sides).")
    if any(s.fs > 1.0 + 1e-9 for s in surfaces if s.region_id in _line_regions(lines)):
        out.append(
            "Some walls were photographed at an angle; their size was adjusted to make up "
            "for it (by at most 40%)."
        )
    if "railing" in labels:
        out.append("Railings are priced by their length along the front of the house.")
    if any(line.companions for line in lines):
        out.append("Primer for paint and adhesive for tiles are added automatically.")
    if scaffolding_on:
        out.append(
            f"Scaffolding is included because the house has {inputs.floors} floors "
            f"(₹{fmt(inputs.extras.scaffolding_rate_per_sqft, 2)} per sq ft of wall)."
        )
    if any(line.rate_overridden for line in lines):
        out.append("Prices you changed are marked and used instead of our typical prices.")
    if skipped:
        out.append("Materials chosen for windows or doors are not priced.")
    out.append(
        "Material wastage (cutting, breakage, spillage) is added, and materials are bought in "
        "whole cans, bags, boxes or sheets."
    )
    out.append(
        "Prices are typical for a large Indian city; please check them against local quotes."
    )
    out.append(
        "Not included: sides and back of the house that are not in the photo, repairs such as "
        "cracks or damp, demolition, debris removal and transport."
    )
    return out


def _line_regions(lines: list[LineItem]) -> set[str]:
    return {r for line in lines for r in line.region_ids}


def estimate_from_surfaces(
    inputs: EstimateInputs,
    surfaces: list[SurfaceMeasure],
    openings: list[SurfaceMeasure],
) -> Estimate:
    """Everything after measurement: lines, extras, range, assumptions, fingerprint."""
    lines, skipped = build_lines(inputs, surfaces)
    subtotals: dict[str, float] = {}
    for line in lines:
        subtotals[line.category] = subtotals.get(line.category, 0.0) + line.total
    lines_total = sum(line.total for line in lines)
    wall_area = sum(
        line.measured_quantity
        for line in lines
        if line.label == "wall" and line.measured_unit == "sqft"
    )
    confidence = inputs.scale.confidence
    totals = apply_extras(lines_total, wall_area, inputs.floors, inputs.extras, confidence)
    return Estimate(
        lines=lines,
        surfaces=surfaces,
        openings=openings,
        category_subtotals=subtotals,
        lines_total=totals.lines_total,
        wall_area_sqft=wall_area,
        scaffolding=totals.scaffolding,
        contingency=totals.contingency,
        tax=totals.tax,
        grand_total=totals.grand_total,
        range_pct=totals.range_pct,
        range_low=totals.range_low,
        range_high=totals.range_high,
        confidence=confidence,
        provisional=not inputs.scale_confirmed,
        scale=inputs.scale,
        extras=inputs.extras,
        assumptions=assumptions_for(
            inputs,
            surfaces,
            lines,
            inputs.floors >= inputs.extras.scaffolding_min_floors and wall_area > 0,
            skipped,
        ),
        fingerprint=estimate_fingerprint(inputs),
    )


def compute_estimate(inputs: EstimateInputs) -> Estimate:
    """Full estimate: quantities, costs, extras, range, fingerprint."""
    surfaces, openings = measure_surfaces(inputs.regions, inputs.scale)
    return estimate_from_surfaces(inputs, surfaces, openings)


__all__ = [
    "RANGE_PCT",
    "Totals",
    "apply_extras",
    "build_lines",
    "compute_estimate",
    "estimate_from_surfaces",
    "price_line",
    "round_money",
]
