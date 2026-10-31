"""Generate a 512 x 512 PNG swatch for every material in seed/materials.json.

Procedural and deterministic (fixed seeds), using only NumPy and Pillow:

    cd apps/api && uv run python ../../seed/make_swatches.py
"""

from __future__ import annotations

import json
import zlib
from collections.abc import Callable
from pathlib import Path

import numpy as np
from PIL import Image

SIZE = 512
HERE = Path(__file__).resolve().parent
OUT = HERE / "swatches"

Array = np.ndarray


# ---------------------------------------------------------------- helpers


def hex_rgb(h: str) -> Array:
    h = h.lstrip("#")
    return np.array([int(h[i : i + 2], 16) for i in (0, 2, 4)], dtype=np.float64)


def value_noise(rng: np.random.Generator, cells: int, size: int = SIZE) -> Array:
    """Smooth noise in [0, 1] from an upscaled random grid."""
    grid = (rng.random((cells + 1, cells + 1)) * 255).astype(np.uint8)
    img = Image.fromarray(grid, "L").resize((size, size), Image.BICUBIC)
    return np.asarray(img, dtype=np.float64) / 255.0


def fractal(rng: np.random.Generator, base: int = 4, octaves: int = 5, size: int = SIZE) -> Array:
    total = np.zeros((size, size))
    amp, norm = 1.0, 0.0
    for o in range(octaves):
        total += amp * value_noise(rng, base * 2**o, size)
        norm += amp
        amp *= 0.5
    return total / norm


def fill(color: Array) -> Array:
    return np.ones((SIZE, SIZE, 3)) * color


def shade(img: Array, factor: Array) -> Array:
    return img * factor[..., None]


def lighting(rng: np.random.Generator, strength: float = 0.06) -> Array:
    """Gentle diagonal light fall-off so swatches do not look flat."""
    y, x = np.mgrid[0:SIZE, 0:SIZE] / SIZE
    return 1 + strength * (0.5 - (x + y) / 2) * 2


def relief(height: Array, strength: float = 6.0) -> Array:
    """Lambert shading of a height map lit from the top left, around 1.0."""
    gy, gx = np.gradient(height)
    nx, ny, nz = -gx * strength * SIZE / 64, -gy * strength * SIZE / 64, np.ones_like(height)
    n = np.sqrt(nx**2 + ny**2 + nz**2)
    light = np.array([-0.5, -0.5, 0.7])
    light /= np.linalg.norm(light)
    lam = (nx * light[0] + ny * light[1] + nz * light[2]) / n
    return 0.55 + 0.5 * lam


def to_image(img: Array) -> Image.Image:
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB")


def grain_noise(rng: np.random.Generator, amount: float) -> Array:
    return (rng.random((SIZE, SIZE)) - 0.5) * amount


# ---------------------------------------------------------------- generators


def paint(rng: np.random.Generator, m: dict) -> Array:
    base = fill(hex_rgb(m["default_color"]))
    f = 1 + (fractal(rng, 3, 4) - 0.5) * 0.05 + grain_noise(rng, 0.03)
    return shade(base, f * lighting(rng, 0.05))


def texture(rng: np.random.Generator, m: dict) -> Array:
    base = fill(hex_rgb(m["default_color"]))
    rough = "roller" in m["id"]
    if rough:  # soft, stretched roller pattern
        h = fractal(rng, 10, 4)
        h = (
            np.asarray(
                Image.fromarray((h * 255).astype(np.uint8))
                .resize((SIZE, SIZE // 3))
                .resize((SIZE, SIZE), Image.BICUBIC),
                dtype=np.float64,
            )
            / 255
        )
        f = relief(h, 5.0)
    else:  # grainy cement texture
        h = fractal(rng, 24, 4) * 0.7 + rng.random((SIZE, SIZE)) * 0.3
        f = relief(h, 3.5)
    return shade(base, f * lighting(rng, 0.05))


def voronoi(rng: np.random.Generator, n: int) -> tuple[Array, Array]:
    """(cell index, border distance) for a jittered Voronoi diagram (tiled at the edges)."""
    pts = rng.random((n, 2)) * SIZE
    y, x = np.mgrid[0:SIZE, 0:SIZE].astype(np.float64)
    warp = (fractal(rng, 6, 3) - 0.5) * 18
    x = x + warp
    y = y + warp.T
    d = np.sqrt((x[..., None] - pts[:, 0]) ** 2 + ((y[..., None] - pts[:, 1]) * 1.6) ** 2)
    order = np.argsort(d, axis=-1)
    idx = order[..., 0]
    d_sorted = np.take_along_axis(d, order[..., :2], axis=-1)
    return idx, d_sorted[..., 1] - d_sorted[..., 0]


def stone(rng: np.random.Generator, m: dict) -> Array:
    idx, border = voronoi(rng, 38)
    palette = np.array(
        [
            [176, 160, 138],
            [150, 138, 122],
            [196, 182, 160],
            [128, 116, 104],
            [168, 142, 112],
            [140, 126, 112],
            [186, 170, 150],
        ],
        dtype=np.float64,
    )
    cell_col = palette[rng.integers(0, len(palette), idx.max() + 1)]
    cell_col *= 0.9 + rng.random((idx.max() + 1, 1)) * 0.2
    img = cell_col[idx]
    h = fractal(rng, 20, 4) + np.clip(border / 14, 0, 1)
    img = shade(img, relief(h, 4.0))
    mortar = border < 5
    mortar_col = np.array([92, 86, 78]) * (0.9 + 0.2 * fractal(rng, 30, 2))[..., None]
    img[mortar] = mortar_col[mortar]
    return shade(img, lighting(rng, 0.06))


def grid_tiles(
    rng: np.random.Generator,
    tile_w: int,
    tile_h: int,
    grout: int,
    colours: Array,
    grout_col: Array,
    surface: Callable[[np.random.Generator], Array],
    stagger: bool = False,
) -> Array:
    y, x = np.mgrid[0:SIZE, 0:SIZE]
    row = y // tile_h
    xo = x + (row % 2) * (tile_w // 2 if stagger else 0)
    col = xo // tile_w
    tile_id = row * 1000 + col
    uniq, inv = np.unique(tile_id, return_inverse=True)
    picks = colours[rng.integers(0, len(colours), len(uniq))]
    picks = picks * (0.92 + rng.random((len(uniq), 1)) * 0.16)
    img = picks[inv.reshape(SIZE, SIZE)]
    img = shade(img, surface(rng))
    in_grout = ((y % tile_h) < grout) | ((xo % tile_w) < grout)
    img[in_grout] = grout_col
    # a soft shadow just under/right of each grout line for depth
    edge = (((y % tile_h) >= grout) & ((y % tile_h) < grout + 2)) | (
        ((xo % tile_w) >= grout) & ((xo % tile_w) < grout + 2)
    )
    img[edge] *= 0.85
    return shade(img, lighting(rng, 0.05))


def slate(rng: np.random.Generator, m: dict) -> Array:
    def surface(r: np.random.Generator) -> Array:
        streak = (
            np.asarray(
                Image.fromarray((fractal(r, 16, 4) * 255).astype(np.uint8))
                .resize((SIZE, 24))
                .resize((SIZE, SIZE), Image.BICUBIC),
                dtype=np.float64,
            )
            / 255
        )
        return relief(streak * 0.6 + fractal(r, 30, 3) * 0.4, 4.0)

    colours = np.array(
        [[92, 96, 100], [110, 104, 98], [128, 98, 76], [80, 84, 90], [140, 116, 90]],
        dtype=np.float64,
    )
    return grid_tiles(rng, 256, 128, 6, colours, np.array([60, 58, 56]), surface, stagger=True)


def ceramic(rng: np.random.Generator, m: dict) -> Array:
    def surface(r: np.random.Generator) -> Array:
        y, x = np.mgrid[0:SIZE, 0:SIZE] / SIZE
        gloss = 1 + 0.08 * np.exp(-(((x - 0.3) ** 2 + (y - 0.25) ** 2) / 0.05))
        return gloss * (1 + (fractal(r, 40, 2) - 0.5) * 0.06)

    colours = np.array([[214, 196, 170], [204, 184, 158], [222, 206, 182]], dtype=np.float64)
    return grid_tiles(rng, 128, 256, 5, colours, np.array([235, 232, 226]), surface)


def vitrified(rng: np.random.Generator, m: dict) -> Array:
    def surface(r: np.random.Generator) -> Array:
        y, x = np.mgrid[0:SIZE, 0:SIZE].astype(np.float64)
        warp = fractal(r, 4, 4) * 40
        veins = np.abs(np.sin((x * 0.6 + y * 0.8) / 38 + warp))
        vein = np.where(veins < 0.06, 0.82 + veins * 3, 1.0)
        return vein * (1 + (fractal(r, 8, 3) - 0.5) * 0.08)

    colours = np.array([[226, 222, 214], [218, 214, 206]], dtype=np.float64)
    return grid_tiles(rng, 256, 256, 3, colours, np.array([200, 196, 188]), surface)


def brick(rng: np.random.Generator, m: dict) -> Array:
    def surface(r: np.random.Generator) -> Array:
        return relief(fractal(r, 40, 4) * 0.6 + r.random((SIZE, SIZE)) * 0.4, 2.5)

    colours = np.array(
        [[160, 74, 48], [146, 66, 44], [176, 88, 58], [132, 60, 42], [168, 96, 66]],
        dtype=np.float64,
    )
    return grid_tiles(rng, 128, 42, 8, colours, np.array([196, 188, 174]), surface, stagger=True)


def acp(rng: np.random.Generator, m: dict) -> Array:
    base = fill(hex_rgb(m["default_color"]))
    y, x = np.mgrid[0:SIZE, 0:SIZE] / SIZE
    metallic = 1 + 0.12 * (0.5 - y) + 0.04 * np.sin(x * 9) + grain_noise(rng, 0.01)
    img = shade(base, metallic)
    yy, xx = np.mgrid[0:SIZE, 0:SIZE]
    joint = ((xx % 256) < 8) | ((yy % 171) < 8)
    img[joint] = [62, 64, 68]
    return img


def wood(rng: np.random.Generator, colour: Array, along_x: bool = True) -> Array:
    y, x = np.mgrid[0:SIZE, 0:SIZE].astype(np.float64)
    warp = fractal(rng, 3, 3) * 30
    coord = y if along_x else x
    rings = np.sin(coord / 3.2 + warp) * 0.5 + 0.5
    fine = fractal(rng, 64, 2)
    return shade(fill(colour), 0.78 + rings * 0.18 + fine * 0.1)


def hpl(rng: np.random.Generator, m: dict) -> Array:
    img = wood(rng, np.array([150, 102, 64]))
    yy, xx = np.mgrid[0:SIZE, 0:SIZE]
    img[((xx % 256) < 6) | ((yy % 512) < 6)] = [40, 32, 26]
    return shade(img, lighting(rng, 0.05))


def wpc(rng: np.random.Generator, m: dict) -> Array:
    img = wood(rng, np.array([132, 92, 60]))
    yy = np.mgrid[0:SIZE, 0:SIZE][0]
    pos = yy % 64
    slat = 1 - 0.25 * ((pos - 26) / 26) ** 2  # rounded slat profile
    img = shade(img, np.where(pos < 52, slat, 1.0))
    gap = pos >= 52
    img[gap] = np.array([34, 30, 28]) * (1 + 0.2 * (pos[gap] - 52) / 12)[..., None]
    return shade(img, lighting(rng, 0.05))


def backdrop(rng: np.random.Generator) -> Array:
    """Light plain wall behind railings and gates."""
    y = np.mgrid[0:SIZE, 0:SIZE][0] / SIZE
    img = fill(np.array([226, 222, 214]))
    return shade(img, 1 - 0.08 * y + (fractal(rng, 3, 3) - 0.5) * 0.04)


def rect(img: Array, x0: int, y0: int, x1: int, y1: int, colour, alpha: float = 1.0) -> None:
    img[y0:y1, x0:x1] = img[y0:y1, x0:x1] * (1 - alpha) + np.asarray(colour) * alpha


def metal_bar(img: Array, x0: int, y0: int, x1: int, y1: int, colour: Array, vertical=True) -> None:
    """Draw a bar with cylindrical shading."""
    n = (x1 - x0) if vertical else (y1 - y0)
    t = np.linspace(-1, 1, max(n, 1))
    prof = 0.65 + 0.5 * np.cos(t * 1.3) ** 2 - 0.15 * t
    if vertical:
        img[y0:y1, x0:x1] = colour * prof[None, :, None]
    else:
        img[y0:y1, x0:x1] = colour * prof[:, None, None]


def glass_railing(rng: np.random.Generator, m: dict) -> Array:
    img = backdrop(rng)
    floor = 440
    rect(img, 0, floor, SIZE, SIZE, [170, 164, 156])
    steel = np.array([200, 204, 208])
    for x0 in (16, 186, 356):
        rect(img, x0 + 18, 96, x0 + 152, floor - 6, [150, 196, 196], 0.35)  # pane
        rect(img, x0 + 18, 96, x0 + 152, 100, [240, 250, 250], 0.7)  # top edge
        # diagonal reflection
        y, x = np.mgrid[96 : floor - 6, x0 + 18 : x0 + 152]
        band = np.abs((x - x0) + (y - 96) * 0.6 - 90) < 10
        sub = img[96 : floor - 6, x0 + 18 : x0 + 152]
        sub[band] = sub[band] * 0.6 + 255 * 0.4
        for cy in (140, floor - 50):  # clamps
            rect(img, x0 + 14, cy, x0 + 30, cy + 22, steel * 0.8)
            rect(img, x0 + 140, cy, x0 + 156, cy + 22, steel * 0.8)
    for px in (6, 176, 346, 496):
        metal_bar(img, px, 80, px + 12, floor, steel)
    metal_bar(img, 0, 72, SIZE, 92, steel, vertical=False)  # handrail
    return img


def ms_railing(rng: np.random.Generator, m: dict) -> Array:
    img = backdrop(rng)
    colour = hex_rgb(m["default_color"]) * 1.4
    floor = 440
    rect(img, 0, floor, SIZE, SIZE, [170, 164, 156])
    for x in range(20, SIZE, 38):
        metal_bar(img, x, 90, x + 12, floor, colour)
    metal_bar(img, 0, 76, SIZE, 98, colour, vertical=False)
    metal_bar(img, 0, 400, SIZE, 414, colour, vertical=False)
    return img


def ss_railing(rng: np.random.Generator, m: dict) -> Array:
    img = backdrop(rng)
    steel = np.array([208, 212, 216])
    floor = 440
    rect(img, 0, floor, SIZE, SIZE, [170, 164, 156])
    for px in (30, 250, 470):
        metal_bar(img, px, 80, px + 18, floor, steel)
    for y in (70, 170, 250, 330):
        h = 22 if y == 70 else 10
        metal_bar(img, 0, y, SIZE, y + h, steel, vertical=False)
    img += grain_noise(rng, 6)[..., None]
    return img


def gate(rng: np.random.Generator, m: dict) -> Array:
    img = backdrop(rng)
    colour = hex_rgb(m["default_color"]) * 1.3
    rect(img, 0, 470, SIZE, SIZE, [150, 146, 140])
    for x0, x1 in ((20, 252), (260, 492)):  # two leaves
        metal_bar(img, x0, 40, x0 + 18, 470, colour)
        metal_bar(img, x1 - 18, 40, x1, 470, colour)
        metal_bar(img, x0, 40, x1, 58, colour, vertical=False)
        metal_bar(img, x0, 452, x1, 470, colour, vertical=False)
        metal_bar(img, x0, 240, x1, 256, colour, vertical=False)
        for x in range(x0 + 34, x1 - 24, 26):
            metal_bar(img, x, 58, x + 10, 452, colour)
        rect(img, x0 + 18, 256, x1 - 18, 452, colour * 0.95, 0.85)  # lower sheet panel
        # small decorative studs on the panel
        for x in range(x0 + 40, x1 - 30, 40):
            rect(img, x, 340, x + 8, 348, colour * 1.4)
    return img


GENERATORS: dict[str, Callable[[np.random.Generator, dict], Array]] = {
    "paint-economy-emulsion": paint,
    "paint-premium-emulsion": paint,
    "paint-elastomeric-weatherproof": paint,
    "texture-dryblend-finish": texture,
    "texture-roller-paint": texture,
    "cladding-natural-stone": stone,
    "cladding-brick-slips": brick,
    "tiles-slate-stone": slate,
    "tiles-ceramic-exterior": ceramic,
    "tiles-vitrified-exterior": vitrified,
    "panel-acp": acp,
    "panel-hpl": hpl,
    "panel-wpc-louvers": wpc,
    "railing-toughened-glass": glass_railing,
    "railing-ms-painted": ms_railing,
    "railing-ss": ss_railing,
    "gate-ms-fabricated": gate,
}


def main() -> None:
    materials = json.loads((HERE / "materials.json").read_text(encoding="utf-8"))
    OUT.mkdir(exist_ok=True)
    for m in materials:
        rng = np.random.default_rng(zlib.crc32(m["id"].encode()))
        img = to_image(GENERATORS[m["id"]](rng, m))
        img.save(OUT / m["swatch"], optimize=True)
        print(f"wrote {m['swatch']}")


if __name__ == "__main__":
    main()
