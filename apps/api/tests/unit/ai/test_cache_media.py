"""File cache and Pillow helpers."""

from PIL import Image as PILImage

from app.ai.cache import FileCache, cache_key
from app.ai.media import closest_aspect_ratio, hex_to_rgb, load_swatch
from app.ai.tracing import jev_cost
from tests.unit.ai.conftest import make_material


def test_cache_roundtrip_and_corruption(tmp_path):
    cache = FileCache(tmp_path)
    key = cache_key("C1", "m", "v1", ["h1"], {"q": 1})
    assert key == cache_key("C1", "m", "v1", ["h1"], {"q": 1})
    assert key != cache_key("C1", "m", "v1", ["h2"], {"q": 1})
    assert cache.get_json(key) is None and cache.get_bytes(key) is None
    cache.put_json(key, {"a": [1, 2]})
    assert cache.get_json(key) == {"a": [1, 2]}
    cache.put_bytes(key, b"PNG")
    assert cache.get_bytes(key) == b"PNG"
    (tmp_path / key[:2] / f"{key}.json").write_text("{broken", encoding="utf-8")
    assert cache.get_json(key) is None


def test_swatches(tmp_path):
    seed = tmp_path / "seed"
    (seed / "swatches").mkdir(parents=True)
    PILImage.new("RGB", (800, 800), (200, 200, 200)).save(seed / "swatches" / "stone.png")
    (seed / "swatches" / "bad.png").write_bytes(b"not an image")
    stone = make_material("stone", ["wall"])
    img = load_swatch(seed, stone)
    assert max(img.size) == 384 and img.getpixel((1, 1)) == (200, 200, 200)
    variant = make_material(
        "stone@ff0000", ["wall"], swatch="stone.png", default_color="#ff0000", colorable=True
    )
    r, g, b = load_swatch(seed, variant).getpixel((1, 1))
    assert r > g and r > b
    missing = make_material("x", ["wall"], swatch="nope.png", default_color="#00f")
    assert load_swatch(seed, missing).getpixel((0, 0)) == (0, 0, 255)
    bad = make_material("bad", ["wall"])
    assert load_swatch(seed, bad).getpixel((0, 0)) == (160, 160, 160)


def test_small_helpers():
    assert hex_to_rgb("#0a0B0c") == (10, 11, 12)
    assert closest_aspect_ratio(1000, 760) == "4:3"
    assert jev_cost(None) is None and jev_cost(1_000_000) == 0.042
