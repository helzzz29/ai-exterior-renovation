"""Material catalogue loading and validation (seed/materials.json)."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import TypeAdapter

from app.domain.models import Material

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CATALOGUE_PATH = REPO_ROOT / "seed" / "materials.json"
DEFAULT_SWATCH_DIR = REPO_ROOT / "seed" / "swatches"

_ADAPTER = TypeAdapter(list[Material])


def check_material(m: Material) -> None:
    """Unit-specific rules that the schema alone cannot express."""
    problems: list[str] = []
    if m.pricing_unit in ("litre", "kg") and not (m.coverage_sqft_per_unit or 0) > 0:
        problems.append("needs a positive coverage_sqft_per_unit")
    if m.pricing_unit in ("piece", "sheet") and not (m.piece_area_sqft or 0) > 0:
        problems.append("needs a positive piece_area_sqft")
    if m.pricing_unit == "rft" and m.measure_basis != "length":
        problems.append("is priced per rft so must be measured by length")
    if m.measure_basis == "length" and m.pricing_unit != "rft":
        problems.append("is measured by length so must be priced per rft")
    if m.coats < 1:
        problems.append("needs at least 1 coat")
    if m.wastage_pct < 0 or m.material_rate < 0 or m.labour_rate < 0:
        problems.append("has a negative rate or wastage")
    if m.pack_size is not None and m.pack_size <= 0:
        problems.append("has a non-positive pack_size")
    if any(size <= 0 for size in m.pack_sizes):
        problems.append("has a non-positive size in pack_sizes")
    if m.pack_sizes and m.pack_size is None:
        problems.append("lists pack_sizes without a pack_size")
    if m.pieces_per_box is not None and m.pieces_per_box <= 0:
        problems.append("has a non-positive pieces_per_box")
    if m.colorable and not m.default_color:
        problems.append("is colourable but has no default_color")
    if not m.applicable_labels:
        problems.append("has no applicable_labels")
    for c in m.companions:
        if c.quantity_per_sqft < 0 or c.pack_size <= 0 or c.rate < 0:
            problems.append(f"has an invalid companion {c.name!r}")
    if problems:
        raise ValueError(f"material {m.id!r} " + "; ".join(problems))


def load_catalogue(path: Path) -> dict[str, Material]:
    """Load and validate seed/materials.json; returns materials by id (file order)."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    materials = _ADAPTER.validate_python(raw)
    out: dict[str, Material] = {}
    for m in materials:
        if m.id in out:
            raise ValueError(f"duplicate material id {m.id!r}")
        check_material(m)
        out[m.id] = m
    return out


def missing_swatches(catalogue: dict[str, Material], swatch_dir: Path) -> list[str]:
    """Material ids whose swatch image file does not exist."""
    return [m.id for m in catalogue.values() if not (Path(swatch_dir) / m.swatch).is_file()]
