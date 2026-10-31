"""Small Pillow helpers for model inputs: encoding, swatches, aspect ratios. No geometry here."""

import io
import math
from pathlib import Path

import structlog
from PIL import Image as PILImage
from PIL import ImageOps
from PIL.Image import Image

from app.domain.models import Material

log = structlog.get_logger(__name__)

SWATCH_SIZE = 384
VARIANT_SEP = "@"  # material id of a colour variant: "<catalogue id>@<hex without #>"

# Aspect ratios accepted by the Gemini image model (ImageConfig.aspect_ratio).
SUPPORTED_ASPECT_RATIOS: tuple[str, ...] = ("1:1", "4:3", "3:4", "3:2", "2:3", "16:9", "9:16")


def encode_png(img: Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=False)
    return buf.getvalue()


def encode_jpeg(img: Image, quality: int = 92) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def decode_image(data: bytes) -> Image:
    img = PILImage.open(io.BytesIO(data))
    img.load()
    return img.convert("RGB")


def closest_aspect_ratio(width: int, height: int) -> str:
    target = math.log(width / height)

    def distance(ratio: str) -> float:
        w, h = (int(p) for p in ratio.split(":"))
        return abs(math.log(w / h) - target)

    return min(SUPPORTED_ASPECT_RATIOS, key=distance)


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    v = value.lstrip("#")
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)


def is_variant(material: Material) -> bool:
    return VARIANT_SEP in material.id


def load_swatch(seed_dir: Path, material: Material) -> Image:
    """Catalogue swatch (seed/swatches/<file>); colour variants are re-tinted to their colour.

    A missing swatch falls back to a flat patch of the material's colour, so a call never fails
    just because an image file is absent.
    """
    path = Path(seed_dir) / "swatches" / material.swatch
    img: Image | None = None
    if path.is_file():
        try:
            img = decode_image(path.read_bytes())
        except OSError:
            log.warning("swatch_unreadable", path=str(path))
    color = hex_to_rgb(material.default_color) if material.default_color else (160, 160, 160)
    if img is None:
        log.warning("swatch_missing", material=material.id, path=str(path))
        img = PILImage.new("RGB", (SWATCH_SIZE, SWATCH_SIZE), color)
    elif is_variant(material) and material.default_color:
        gray = ImageOps.grayscale(img)
        dark = tuple(int(c * 0.55) for c in color)
        light = tuple(min(255, int(c * 1.15) + 10) for c in color)
        img = ImageOps.colorize(gray, black=dark, white=light)  # type: ignore[arg-type]
    img.thumbnail((SWATCH_SIZE, SWATCH_SIZE))
    return img
