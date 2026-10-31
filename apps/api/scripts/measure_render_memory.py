"""Measure memory of the new-look pipeline at production image size, with no network calls.

Runs the real render loop (zone map -> composite -> check prep, auto-regenerating) with a stub
provider that returns full-size images and always fails the check, so every attempt runs, then
saves the result the way a render job does. Prints baseline and peak resident memory.

    uv run python scripts/measure_render_memory.py --renders 2
(on Windows add `--with psutil` to `uv run`; Linux reads /proc.)
"""

import argparse
import asyncio
import sys
from pathlib import Path

import numpy as np
from PIL import Image as PILImage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.jobs.tasks  # noqa: E402, F401  (load what the production process loads)
from app import imaging  # noqa: E402
from app.ai import render_design  # noqa: E402
from app.domain.models import Assignment, QAResult, Region  # noqa: E402
from app.services.catalogue import get_catalogue  # noqa: E402
from app.services.images import encode_off_loop  # noqa: E402
from app.services.observability import memory_mb  # noqa: E402

WALL = "cladding-natural-stone"
PILLAR = "paint-premium-emulsion"


def mem() -> tuple[float, float]:
    current, peak = memory_mb()
    if current is not None and peak is not None:
        return current, peak
    import psutil  # Windows fallback for local runs

    info = psutil.Process().memory_info()
    return info.rss / 2**20, info.peak_wset / 2**20


def noise(width: int, height: int, seed: int) -> PILImage.Image:
    rng = np.random.default_rng(seed)
    return PILImage.fromarray(rng.integers(0, 255, (height, width, 3), np.uint8))


def rect(x0: int, y0: int, x1: int, y1: int) -> list[tuple[int, int]]:
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def scene(width: int, height: int) -> tuple[list[Region], list[Assignment]]:
    cols = 6
    step = width // cols
    regions = [
        Region(id=f"w{i}", label="wall", polygon=rect(i * step, 0, (i + 1) * step - 1, height // 2))
        for i in range(cols)
    ]
    regions.append(Region(id="p1", label="pillar", polygon=rect(0, height // 2, 80, height - 1)))
    regions.append(Region(id="win", label="window", polygon=rect(200, 100, 400, 300)))
    assignments = [Assignment(region_id=r.id, material_id=WALL) for r in regions[:cols]]
    assignments.append(Assignment(region_id="p1", material_id=PILLAR, color="#aa5533"))
    return regions, assignments


class StubProvider:
    """Full-size images like the image model's 2K reply; the check always fails."""

    def __init__(self, width: int, height: int, seed: int) -> None:
        self.size = (width, height)
        self.seed = seed

    async def generate_redesign(
        self, photo, zone_map, zones, materials, user_note=None, fix_notes=None, attempt=0
    ):
        await asyncio.sleep(0.05)  # network wait: lets concurrent renders interleave
        return noise(*self.size, seed=self.seed * 10 + attempt)

    async def check_render(self, original, result, zone_map, zones, materials):
        for img in (original, result, zone_map):
            imaging.to_jev_jpeg(img)
        await asyncio.sleep(0.05)
        scores = {z.color_name: 0.3 for z in zones}
        return QAResult(openings_preserved=0.3, structure_preserved=0.3, zones=scores, passed=False)


async def one_render(width: int, height: int, seed: int, max_regen: int) -> None:
    regions, assignments = scene(width, height)
    photo = noise(width, height, seed=seed)
    outcome = await render_design(
        StubProvider(width, height, seed),
        photo,
        regions,
        assignments,
        get_catalogue(),
        None,
        max_regen,
        0.6,
    )
    await encode_off_loop(outcome.image, "JPEG")  # what store_image does
    await encode_off_loop(outcome.zone_map, "PNG")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--renders", type=int, default=1, help="renders running at once")
    parser.add_argument("--width", type=int, default=2048)
    parser.add_argument("--height", type=int, default=1536)
    parser.add_argument("--max-regen", type=int, default=2)
    args = parser.parse_args()

    base, _ = mem()
    await asyncio.gather(
        *(one_render(args.width, args.height, i, args.max_regen) for i in range(args.renders))
    )
    current, peak = mem()
    print(
        f"renders={args.renders} size={args.width}x{args.height} "
        f"attempts={1 + args.max_regen} | baseline {base:.0f} MB | peak {peak:.0f} MB "
        f"(+{peak - base:.0f} MB over baseline) | after {current:.0f} MB"
    )


if __name__ == "__main__":
    asyncio.run(main())
