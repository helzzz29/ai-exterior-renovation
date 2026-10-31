"""Material catalogue, loaded once from seed/materials.json through the estimation package."""

from app import estimation
from app.config import get_settings
from app.domain.models import Material

_cache: dict[str, Material] | None = None


def get_catalogue() -> dict[str, Material]:
    global _cache
    if _cache is None:
        _cache = estimation.load_catalogue(get_settings().seed_dir / "materials.json")
    return _cache


def reset_catalogue() -> None:
    global _cache
    _cache = None


def swatch_url(material: Material) -> str:
    return f"/api/swatches/{material.swatch.lstrip('/')}"
