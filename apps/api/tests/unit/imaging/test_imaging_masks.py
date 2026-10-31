import base64
import io
import logging
import math

import pytest
from PIL import Image, ImageDraw

from app.domain.ai import GeminiSegment
from app.domain.models import BoxPx, SegmentCandidate
from app.imaging import polygon_area_px, resolve_overlaps, segments_to_candidates

W, H = 1000, 800


def png_b64(img: Image.Image, prefix: bool = False) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    text = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/png;base64,{text}" if prefix else text


def box_2d(x0: int, y0: int, x1: int, y1: int) -> list[int]:
    """Pixel box -> Gemini [y0, x0, y1, x1] normalised to 0-1000."""
    return [round(y0 / H * 1000), round(x0 / W * 1000), round(y1 / H * 1000), round(x1 / W * 1000)]


def seg(label: str, box: tuple[int, int, int, int], mask: str) -> GeminiSegment:
    return GeminiSegment(label=label, box_2d=box_2d(*box), mask=mask)


@pytest.mark.parametrize("prefix", [False, True])
def test_rectangle_mask_area(prefix: bool) -> None:
    # Mask fills the inner rectangle [64:192, 32:224] of a 256x256 probability map.
    mask = Image.new("L", (256, 256), 0)
    ImageDraw.Draw(mask).rectangle((32, 64, 223, 191), fill=255)
    box = (100, 200, 500, 600)  # 400 x 400 px
    out = segments_to_candidates([seg(" Wall ", box, png_b64(mask, prefix))], W, H)
    assert len(out) == 1
    cand = out[0]
    assert cand.label_hint == "wall"
    truth = (400 * 192 / 256) * (400 * 128 / 256)
    assert polygon_area_px(cand.polygon) == pytest.approx(truth, rel=0.03)
    assert cand.box.x0 == pytest.approx(150, abs=3)
    assert cand.box.y0 == pytest.approx(300, abs=3)
    assert cand.box.x1 == pytest.approx(450, abs=3)
    assert cand.box.y1 == pytest.approx(500, abs=3)
    assert all(isinstance(v, float) for p in cand.polygon for v in p)


def test_ellipse_mask_area() -> None:
    mask = Image.new("L", (200, 150), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, 199, 149), fill=230)
    box = (200, 100, 600, 400)  # 400 x 300
    out = segments_to_candidates([seg("window", box, png_b64(mask))], W, H)
    assert len(out) == 1
    truth = math.pi * 200 * 150
    assert polygon_area_px(out[0].polygon) == pytest.approx(truth, rel=0.03)


def test_two_blobs_two_candidates_and_tiny_blob_dropped() -> None:
    mask = Image.new("L", (200, 100), 0)
    draw = ImageDraw.Draw(mask)
    draw.rectangle((0, 0, 79, 99), fill=255)
    draw.rectangle((120, 0, 199, 99), fill=255)
    draw.rectangle((95, 45, 99, 49), fill=255)  # tiny blob, well under 0.2% of image
    out = segments_to_candidates([seg("pillar", (0, 0, 400, 200), png_b64(mask))], W, H)
    assert len(out) == 2
    xs = sorted(c.box.x0 for c in out)
    assert xs[0] == pytest.approx(0, abs=2)
    assert xs[1] == pytest.approx(240, abs=3)
    for c in out:
        assert polygon_area_px(c.polygon) == pytest.approx(160 * 200, rel=0.03)


def test_small_component_threshold() -> None:
    # 0.2% of 1000x800 = 1600 px. A 30x30 blob (900 px) goes, a 50x50 (2500 px) stays.
    mask = Image.new("L", (100, 100), 0)
    ImageDraw.Draw(mask).rectangle((0, 0, 29, 29), fill=255)
    ImageDraw.Draw(mask).rectangle((50, 50, 99, 99), fill=255)
    out = segments_to_candidates([seg("door", (0, 0, 100, 100), png_b64(mask))], W, H)
    assert len(out) == 1
    assert out[0].box.x0 == pytest.approx(50, abs=1)


def test_malformed_segments_are_skipped(caplog: pytest.LogCaptureFixture) -> None:
    good = Image.new("L", (10, 10), 255)
    segments = [
        GeminiSegment(label="wall", box_2d=[0, 0, 500], mask=png_b64(good)),  # wrong length
        GeminiSegment(label="wall", box_2d=[500, 500, 500, 900], mask=png_b64(good)),  # flat
        seg("wall", (0, 0, 200, 200), "!!!not base64!!!"),
        seg("wall", (0, 0, 200, 200), base64.b64encode(b"not a png").decode()),
        seg("door", (300, 300, 500, 500), png_b64(good)),
    ]
    with caplog.at_level(logging.WARNING, logger="app.imaging.masks"):
        out = segments_to_candidates(segments, W, H)
    assert [c.label_hint for c in out] == ["door"]
    assert len([r for r in caplog.records if "skipping" in r.message]) == 4


@pytest.mark.parametrize("mask", ["", "data:image/png;base64,", None])
def test_missing_or_empty_mask_falls_back_to_box(mask: str | None) -> None:
    if mask is None:
        mask = png_b64(Image.new("L", (20, 20), 0))  # decodes, but nothing above threshold
    out = segments_to_candidates([seg("Balcony", (100, 80, 300, 240), mask)], W, H)
    assert len(out) == 1
    cand = out[0]
    assert cand.label_hint == "balcony"
    assert cand.polygon == [(100, 80), (300, 80), (300, 240), (100, 240)]
    assert cand.box == BoxPx(x0=100, y0=80, x1=300, y1=240)


def test_box_fallback_respects_min_area() -> None:
    out = segments_to_candidates([seg("window", (0, 0, 20, 20), "")], W, H)
    assert out == []


def test_box_is_clamped_to_image() -> None:
    full = png_b64(Image.new("L", (16, 16), 255))
    out = segments_to_candidates(
        [GeminiSegment(label="wall", box_2d=[-50, -50, 1200, 1200], mask=full)], W, H
    )
    assert len(out) == 1
    assert out[0].box == BoxPx(x0=0, y0=0, x1=W, y1=H)


def test_reversed_box_coordinates_are_ordered() -> None:
    full = png_b64(Image.new("L", (16, 16), 255))
    out = segments_to_candidates(
        [GeminiSegment(label="wall", box_2d=[500, 500, 0, 0], mask=full)], W, H
    )
    assert len(out) == 1
    assert out[0].box.x1 == pytest.approx(500, abs=1)


# ---------------------------------------------------------------- overlaps


def cand(label: str, x0: float, y0: float, x1: float, y1: float) -> SegmentCandidate:
    return SegmentCandidate(
        label_hint=label,
        polygon=[(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
        box=BoxPx(x0=x0, y0=y0, x1=x1, y1=y1),
    )


def test_resolve_overlaps_clips_lower_priority() -> None:
    wall = cand("wall", 0, 0, 100, 100)
    pillar = cand("pillar", 80, 0, 120, 100)
    out = resolve_overlaps([wall, pillar])
    assert [c.label_hint for c in out] == ["wall", "pillar"]
    assert polygon_area_px(out[0].polygon) == pytest.approx(80 * 100)
    assert polygon_area_px(out[1].polygon) == pytest.approx(40 * 100)
    assert out[0].box.x1 == pytest.approx(80)


def test_resolve_overlaps_contained_and_split() -> None:
    wall = cand("wall", 0, 0, 100, 100)
    window = cand("window", 40, 40, 60, 60)  # fully inside: wall unchanged (no holes)
    railing = cand("railing", 0, 45, 100, 55)  # cuts a parapet in two
    parapet = cand("parapet", 10, 0, 30, 100)
    unknown = cand("tree", 0, 0, 5, 5)
    out = resolve_overlaps([wall, window, parapet, railing, unknown], min_area_px=1)
    labels = [c.label_hint for c in out]
    assert labels.count("parapet") == 2
    assert "tree" not in labels  # fully covered by the wall (higher priority than unknown)
    wall_out = next(c for c in out if c.label_hint == "wall")
    assert polygon_area_px(wall_out.polygon) > 0
