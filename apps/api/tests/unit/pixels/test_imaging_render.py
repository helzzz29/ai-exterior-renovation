import numpy as np
import pytest
from PIL import Image

from renocore.pixels import composite, composite_alpha, polygons_mask, region_crop, zone_map


def noise(w: int, h: int, seed: int = 0) -> Image.Image:
    rng = np.random.default_rng(seed)
    return Image.fromarray(rng.integers(0, 256, (h, w, 3), dtype=np.uint8))


def rect(x0: float, y0: float, x1: float, y1: float) -> list[tuple[float, float]]:
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


# ---------------------------------------------------------------- region_crop


def test_region_crop_padding_and_outline() -> None:
    img = Image.new("RGB", (1000, 800), (40, 160, 40))
    crop = region_crop(img, rect(400, 300, 600, 500))
    assert crop.size == (300, 300)  # 200 px box + 50 px each side
    arr = np.asarray(crop)
    red = (arr[..., 0] == 255) & (arr[..., 1] == 0) & (arr[..., 2] == 0)
    assert red.sum() > 4 * 200 * 2 * 0.9  # outline at least 2 px wide around the box
    assert red[50, 150]  # top edge at crop y=50
    assert not red[150, 150]  # centre untouched
    assert tuple(arr[150, 150]) == (40, 160, 40)


def test_region_crop_no_outline_and_custom_pad() -> None:
    img = noise(400, 300)
    crop = region_crop(img, rect(100, 100, 200, 150), pad=0.0, outline=False)
    assert crop.size == (100, 50)
    assert np.array_equal(np.asarray(crop), np.asarray(img)[100:150, 100:200])


def test_region_crop_clamps_to_image() -> None:
    img = Image.new("RGB", (500, 400), (0, 0, 0))
    crop = region_crop(img, rect(0, 0, 100, 100))
    assert crop.size == (125, 125)
    crop = region_crop(img, rect(450, 350, 500, 400))
    assert crop.size == (63, 63)


def test_region_crop_outline_width_scales() -> None:
    img = Image.new("RGB", (3000, 3000), (0, 0, 0))
    crop = region_crop(img, rect(500, 500, 2500, 2500), pad=0.0)
    arr = np.asarray(crop)
    red_rows = np.where(arr[:, 1000, 0] == 255)[0]
    # width = round(0.006 * 2000) = 12, roughly half of it inside the crop on the top edge
    assert 5 <= len(red_rows[red_rows < 100]) <= 13


def test_region_crop_degenerate_polygon() -> None:
    img = Image.new("RGB", (100, 100), (0, 0, 0))
    crop = region_crop(img, [(100, 100), (100, 100), (100, 100)])
    assert crop.size[0] >= 1 and crop.size[1] >= 1


# ---------------------------------------------------------------- zone_map


def test_zone_map_colours_and_dimming() -> None:
    img = Image.new("RGB", (400, 300), (200, 100, 50))
    zones = [
        ([rect(10, 10, 100, 100)], (255, 0, 0)),
        ([rect(200, 50, 300, 150), rect(320, 200, 390, 290)], (0, 0, 255)),
    ]
    out = zone_map(img, zones)
    assert out.size == img.size and out.mode == "RGB"
    arr = np.asarray(out)
    assert np.all(arr[10:101, 10:101] == (255, 0, 0))
    assert np.all(arr[50:151, 200:301] == (0, 0, 255))
    assert np.all(arr[200:291, 320:391] == (0, 0, 255))
    outside = arr[250, 50].astype(int)
    # golden value: (0.7*rgb + 0.3*mean) * 0.45 with mean = 116.67
    assert np.abs(outside - np.array([78.75, 47.25, 31.5])).max() <= 1
    assert outside.max() < 100


def test_zone_map_exact_colours_no_antialiasing() -> None:
    img = noise(300, 300)
    tri = [(20.0, 20.0), (280.0, 40.0), (150.0, 270.0)]
    out = np.asarray(zone_map(img, [([tri], (0, 255, 0))]))
    mask = polygons_mask((300, 300), [tri]) > 0
    assert np.all(out[mask] == (0, 255, 0))
    # outside the polygon the photo is dimmed, so nothing reaches full brightness
    assert out[~mask].max() <= 115


def test_zone_map_later_zone_wins_overlap() -> None:
    img = Image.new("RGB", (100, 100), (0, 0, 0))
    out = np.asarray(
        zone_map(img, [([rect(0, 0, 60, 60)], (255, 0, 0)), ([rect(40, 40, 99, 99)], (0, 0, 255))])
    )
    assert tuple(out[50, 50]) == (0, 0, 255)
    assert tuple(out[10, 10]) == (255, 0, 0)


def test_zone_map_matches_full_float_formula() -> None:
    """Channel-by-channel dimming is bit-identical to the whole-image float version."""
    img = noise(320, 240, seed=7)
    arr = np.asarray(img, dtype=np.float32)
    grey = arr.mean(axis=2, keepdims=True)
    reference = np.clip(np.round((0.7 * arr + 0.3 * grey) * 0.45), 0, 255).astype(np.uint8)
    assert np.array_equal(np.asarray(zone_map(img, [])), reference)


# ---------------------------------------------------------------- composite


def test_composite_outside_mask_byte_identical() -> None:
    original = noise(400, 300, seed=1)
    generated = noise(400, 300, seed=2)
    include = [rect(50, 50, 250, 250)]
    exclude = [rect(100, 100, 150, 150)]
    out = composite(original, generated, include, exclude)
    o, g, r = (np.asarray(x) for x in (original, generated, out))
    mask = polygons_mask((400, 300), include)
    mask[polygons_mask((400, 300), exclude) > 0] = 0
    outside = mask == 0
    assert np.array_equal(r[outside], o[outside])
    # exclude hole respected
    assert np.array_equal(r[100:151, 100:151], o[100:151, 100:151])
    # deep inside the mask the generated pixels are used
    assert np.array_equal(r[200:240, 60:240], g[200:240, 60:240])
    assert out.mode == "RGB" and out.size == original.size


def float_blend(original, generated, alpha) -> np.ndarray:
    """The exact float blend the 8-bit mask approximates."""
    a = alpha[..., None]
    o = np.asarray(original, dtype=np.float32)
    g = np.asarray(generated, dtype=np.float32)
    return np.clip(np.round(g * a + o * (1.0 - a)), 0, 255).astype(np.uint8)


def test_composite_feathered_edge_within_one_level_of_float_blend() -> None:
    original = noise(400, 300, seed=4)
    generated = noise(400, 300, seed=5)
    include = [rect(40, 40, 360, 260), [(10.0, 290.0), (120.0, 200.0), (200.0, 295.0)]]
    exclude = [rect(150, 100, 220, 180)]
    alpha = composite_alpha((400, 300), include, exclude, feather_px=3)
    edge = (alpha > 0) & (alpha < 1)
    assert edge.sum() > 500  # the test really covers a feathered edge
    out = np.asarray(composite(original, generated, include, exclude), dtype=np.int16)
    diff = np.abs(out - float_blend(original, generated, alpha).astype(np.int16))
    assert diff.max() <= 1
    o = np.asarray(original)
    assert np.array_equal(out[alpha == 0], o[alpha == 0])


def test_composite_feather_ramps_inward() -> None:
    alpha = composite_alpha((200, 200), [rect(50, 50, 150, 150)], [], feather_px=3)
    assert alpha[100, 49] == 0.0
    assert alpha[100, 30] == 0.0
    assert 0.0 <= alpha[100, 50] < 0.5
    assert alpha[100, 100] == pytest.approx(1.0)
    row = alpha[100, 50:60]
    assert np.all(np.diff(row) >= -1e-6)


def test_composite_without_feather() -> None:
    alpha = composite_alpha((50, 50), [rect(10, 10, 40, 40)], [rect(20, 20, 30, 30)], 0)
    assert alpha[15, 15] == 1.0 and alpha[25, 25] == 0.0 and alpha[5, 5] == 0.0


def test_composite_different_aspect_ratio() -> None:
    original = Image.new("RGB", (400, 300), (10, 10, 10))
    # Generated 2:1 with a red centre band matching 4:3 and blue side bars that must be cropped.
    generated = Image.new("RGB", (1200, 600), (0, 0, 255))
    generated.paste((255, 0, 0), (200, 0, 1000, 600))
    out = composite(original, generated, [rect(0, 0, 399, 299)], [], feather_px=0)
    arr = np.asarray(out)
    assert tuple(arr[150, 5]) == (255, 0, 0)
    assert tuple(arr[150, 395]) == (255, 0, 0)
    # taller generated image is cropped top/bottom
    generated = Image.new("RGB", (400, 600), (0, 0, 255))
    generated.paste((0, 255, 0), (0, 150, 400, 450))
    arr = np.asarray(composite(original, generated, [rect(0, 0, 399, 299)], [], feather_px=0))
    assert tuple(arr[5, 200]) == (0, 255, 0)
    assert tuple(arr[295, 200]) == (0, 255, 0)


def test_composite_same_aspect_resize_and_empty_mask() -> None:
    original = noise(200, 100, seed=3)
    generated = Image.new("RGBA", (400, 200), (255, 255, 255, 255))
    out = composite(original, generated, [], [])
    assert np.array_equal(np.asarray(out), np.asarray(original))
    out = composite(original, generated, [rect(0, 0, 199, 99)], [], feather_px=0)
    assert np.all(np.asarray(out) == 255)
