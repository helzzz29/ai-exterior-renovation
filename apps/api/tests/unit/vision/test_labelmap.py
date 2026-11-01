"""C2 label-map mode: decoder (real fixture + synthetic maps) and the request/re-ask flow."""

import io
from collections import Counter
from pathlib import Path

import pytest
from google.genai import types
from PIL import Image as PILImage
from PIL import ImageDraw

from renocore.vision.legend import class_pixels, decode_label_map
from renocore.vision.memo import FileCache
from renocore.vision.payloads import encode_png
from renocore.vision.stages import partition as segment
from renocore.vision.templates import load_prompt
from tests.unit.vision.conftest import FakeGeminiSDK, image_response, make_gemini, text_response

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "ai"


def area(poly) -> float:
    n = len(poly)
    return (
        abs(
            sum(
                poly[i][0] * poly[(i + 1) % n][1] - poly[(i + 1) % n][0] * poly[i][1]
                for i in range(n)
            )
        )
        / 2
    )


def synthetic(size=(1000, 750)) -> PILImage.Image:
    """Black background, red wall, 2 windows, door, pillar, thin roof edge, tall roof."""
    img = PILImage.new("RGB", size, (0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle((100, 200, 900, 700), fill=(255, 0, 0))  # wall
    d.rectangle((200, 300, 300, 450), fill=(0, 0, 255))  # window
    d.rectangle((600, 300, 700, 450), fill=(0, 0, 255))  # window
    d.rectangle((420, 480, 520, 700), fill=(0, 255, 0))  # door
    d.rectangle((100, 200, 140, 700), fill=(255, 0, 255))  # pillar
    d.rectangle((100, 170, 900, 199), fill=(255, 255, 255))  # thin roof edge band (4%)
    d.rectangle((300, 0, 700, 160), fill=(255, 255, 255))  # roof surface (21%): dropped
    d.rectangle((850, 50, 853, 53), fill=(0, 255, 255))  # speck: dropped
    return img


def counts(cands) -> Counter:
    return Counter(c.label_hint for c in cands)


# ---------------------------------------------------------------- decoder


def test_real_fixture_pair():
    photo = PILImage.open(FIXTURES / "house-02.jpg")
    label_map = PILImage.open(FIXTURES / "house-02.labelmap.jpg")
    assert photo.size == (2400, 1800) and label_map.size == (1200, 896)
    w, h = 2048, 1536  # working copy of the photo
    cands = decode_label_map(label_map, w, h)
    c = counts(cands)
    assert c["window"] >= 6 and c["door"] == 1 and c["pillar"] == 2 and c["parapet"] == 2
    assert c["balcony"] >= 1 and c["roof_edge"] == 2  # the big sloped roof is dropped
    walls = [x for x in cands if x.label_hint == "wall"]
    assert sum(area(x.polygon) for x in walls) > 0.25 * w * h
    assert max(area(x.polygon) for x in walls) > 0.15 * w * h
    for x in cands:
        assert all(0 <= px <= w and 0 <= py <= h for px, py in x.polygon)
        assert len(x.polygon) >= 3


def test_synthetic_exact_colours():
    cands = decode_label_map(synthetic(), 1000, 750)
    assert counts(cands) == Counter(
        {"wall": 1, "window": 2, "door": 1, "pillar": 1, "roof_edge": 1}
    )
    door = next(x for x in cands if x.label_hint == "door")
    assert (door.box.x0, door.box.y0) == (420, 480)
    assert abs(area(door.polygon) - 100 * 220) < 50  # contour through pixel centres
    windows = [x for x in cands if x.label_hint == "window"]
    assert windows[0].box.x0 < windows[1].box.x0  # sorted top-to-bottom, left-to-right


def test_jpeg_noise_and_off_palette_colours():
    img = synthetic()
    d = ImageDraw.Draw(img)
    d.rectangle((0, 720, 1000, 749), fill=(128, 128, 128))  # grey: far from palette
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=60)
    noisy = PILImage.open(io.BytesIO(buf.getvalue()))
    assert counts(decode_label_map(noisy, 1000, 750)) == counts(
        decode_label_map(synthetic(), 1000, 750)
    )
    pixels = class_pixels(noisy)
    assert pixels["wall"] > 200_000 and pixels["background"] > 0


def test_size_mismatch_is_rescaled():
    small = synthetic().resize((600, 448), PILImage.NEAREST)  # different aspect too
    cands = decode_label_map(small, 2000, 1500)
    door = next(x for x in cands if x.label_hint == "door")
    assert abs(door.box.x0 - 840) < 8 and abs(door.box.y0 - 960) < 10
    assert counts(cands)["window"] == 2


def test_small_windows_survive_but_specks_do_not():
    img = PILImage.new("RGB", (1000, 1000), (255, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle((10, 10, 35, 35), fill=(0, 0, 255))  # 0.07% window: kept
    d.rectangle((500, 500, 530, 530), fill=(255, 0, 255))  # 0.1% pillar: dropped
    c = counts(decode_label_map(img, 1000, 1000))
    assert c == Counter({"wall": 1, "window": 1})


# ---------------------------------------------------------------- request / flow


@pytest.fixture(autouse=True)
def default_mode(monkeypatch):
    monkeypatch.delenv(segment.SEGMENT_MODE_ENV, raising=False)


def jpeg_bytes(img) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def test_labelmap_request_snapshot():
    assert segment.output_mode() == "labelmap"
    contents = segment.build_labelmap_contents(b"JPEG")
    assert contents[0].inline_data.data == b"JPEG"
    assert contents[0].inline_data.mime_type == "image/jpeg"
    assert contents[1] == load_prompt("segment_v3")
    assert "pure red (255,0,0)" in contents[1] and "black (0,0,0)" in contents[1]
    config = segment.build_labelmap_config(2400, 1800)
    assert config.response_modalities == ["IMAGE"]
    assert config.image_config.aspect_ratio == "4:3"
    assert config.image_config.image_size == "1K"
    reask = segment.build_labelmap_contents(b"J", "no image was returned.")
    assert "could not be used: no image was returned." in reask[1]


async def test_labelmap_run_uses_image_model_and_cache(tmp_path, recorder):
    photo = PILImage.new("RGB", (1000, 750), (120, 120, 120))
    sdk = FakeGeminiSDK([image_response(jpeg_bytes(synthetic()))])
    gem = make_gemini(sdk, recorder)
    cache = FileCache(tmp_path)
    cands = await segment.run(gem, cache, "seg-model", photo, image_model="image-model")
    assert counts(cands)["window"] == 2
    assert sdk.calls[0]["model"] == "image-model"
    rec = recorder.calls[0]
    assert rec.prompt_version == "segment_v3" and rec.output["counts"]["wall"] == 1
    again = await segment.run(gem, cache, "seg-model", photo, image_model="image-model")
    assert len(sdk.calls) == 1 and counts(again) == counts(cands)
    assert recorder.calls[-1].cached


async def test_labelmap_reasks_once_without_image_or_wall(recorder):
    photo = PILImage.new("RGB", (400, 300))
    no_wall = image_response(encode_png(PILImage.new("RGB", (40, 30), (0, 0, 255))))
    sdk = FakeGeminiSDK([text_response("cannot"), image_response(jpeg_bytes(synthetic()))])
    out = await segment.run(make_gemini(sdk, recorder), None, "m", photo)
    assert counts(out)["wall"] == 1 and len(sdk.calls) == 2
    assert "no image was returned (cannot)" in sdk.calls[1]["contents"][1]
    assert recorder.calls[0].error.startswith("invalid output (attempt 1)")

    sdk = FakeGeminiSDK([no_wall, no_wall])
    with pytest.raises(segment.SegmentationError, match="no red wall"):
        await segment.run(make_gemini(sdk), None, "m", photo)
    assert len(sdk.calls) == 2


async def test_labelmap_unreadable_image():
    bad = types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(
                    parts=[types.Part(inline_data=types.Blob(data=b"junk", mime_type="image/png"))]
                )
            )
        ]
    )
    sdk = FakeGeminiSDK([bad, bad])
    with pytest.raises(segment.SegmentationError, match="could not be read"):
        await segment.run(make_gemini(sdk), None, "m", PILImage.new("RGB", (40, 30)))
