"""Estimation engine.

Public interface - keep these names and signatures:
``resolve_scale``, ``measure_surfaces``, ``compute_estimate``, ``fingerprint``,
``load_catalogue``. Smaller building blocks are re-exported for testing and reuse.
"""

from .calibration import (
    DOOR_HEIGHT_FT,
    STOREY_HEIGHT_FT,
    WINDOW_HEIGHT_FT,
    resolve_scale,
    scale_from_door,
    scale_from_floors,
    scale_from_measurement,
    scale_from_windows,
    silhouette,
)
from .price_book import (
    DEFAULT_CATALOGUE_PATH,
    DEFAULT_SWATCH_DIR,
    check_material,
    load_catalogue,
    missing_swatches,
)
from .pricing import (
    RANGE_PCT,
    Totals,
    apply_extras,
    build_lines,
    compute_estimate,
    estimate_from_surfaces,
    price_line,
    round_money,
)
from .signature import canonical_json, estimate_fingerprint, fingerprint
from .surfaces import (
    FS_CAP,
    area_from_px,
    best_fit_quad,
    foreshortening,
    length_from_px,
    measure_region,
    measure_surfaces,
    net_geometries,
    pillar_area,
)
from .takeoff import (
    Quantity,
    best_packs,
    ceil_safe,
    companion_quantity,
    material_quantity,
    round_to_packs,
    with_wastage,
)

__all__ = [
    "DEFAULT_CATALOGUE_PATH",
    "DEFAULT_SWATCH_DIR",
    "DOOR_HEIGHT_FT",
    "FS_CAP",
    "RANGE_PCT",
    "STOREY_HEIGHT_FT",
    "WINDOW_HEIGHT_FT",
    "Quantity",
    "Totals",
    "apply_extras",
    "area_from_px",
    "best_fit_quad",
    "build_lines",
    "canonical_json",
    "ceil_safe",
    "check_material",
    "companion_quantity",
    "compute_estimate",
    "estimate_fingerprint",
    "estimate_from_surfaces",
    "fingerprint",
    "foreshortening",
    "length_from_px",
    "load_catalogue",
    "material_quantity",
    "measure_region",
    "measure_surfaces",
    "missing_swatches",
    "net_geometries",
    "pillar_area",
    "price_line",
    "resolve_scale",
    "round_money",
    "best_packs",
    "round_to_packs",
    "scale_from_door",
    "scale_from_floors",
    "scale_from_measurement",
    "scale_from_windows",
    "silhouette",
    "with_wastage",
]
