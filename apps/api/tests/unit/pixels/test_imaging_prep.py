import io
import struct
import zlib

import numpy as np
import pytest
from PIL import Image, ImageFilter

from renocore.pixels import (
    ImageRejected,
    check_photo,
    load_upload,
    make_working_copy,
    to_jev_jpeg,
)
from renocore.pixels import (
    preprocess as prep,
)


def encode(img: Image.Image, fmt: str, **kwargs) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format=fmt, **kwargs)
    return buf.getvalue()


def checkerboard(w: int = 1200, h: int = 1000, lo: int = 70, hi: int = 180) -> Image.Image:
    yy, xx = np.mgrid[0:h, 0:w]
    arr = np.where(((xx // 20) + (yy // 20)) % 2 == 0, lo, hi).astype(np.uint8)
    return Image.fromarray(np.stack([arr] * 3, -1))


def codes(result) -> dict[str, str]:
    return {i.code: i.severity for i in result.issues}


# ---------------------------------------------------------------- load_upload


@pytest.mark.parametrize("fmt", ["JPEG", "PNG", "WEBP"])
def test_load_upload_accepts_supported_formats(fmt: str) -> None:
    src = Image.new("RGB", (64, 48), (10, 120, 200))
    img = load_upload(encode(src, fmt))
    assert img.mode == "RGB"
    assert img.size == (64, 48)


def test_load_upload_converts_rgba_and_grayscale() -> None:
    rgba = Image.new("RGBA", (10, 10), (255, 0, 0, 0))
    assert load_upload(encode(rgba, "PNG")).getpixel((0, 0)) == (255, 255, 255)
    gray = Image.new("L", (10, 10), 77)
    assert load_upload(encode(gray, "PNG")).getpixel((3, 3)) == (77, 77, 77)
    g16 = Image.new("I;16", (10, 10), 65535)
    assert load_upload(encode(g16, "PNG")).getpixel((3, 3)) == (255, 255, 255)
    pal = Image.new("P", (10, 10), 0)
    pal.info["transparency"] = 0
    assert load_upload(encode(pal, "PNG", transparency=0)).mode == "RGB"


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"GIF89a" + b"\x00" * 50,
        b"\x00\x00\x00\x18ftypheic" + b"\x00" * 50,
        b"hello world, not an image",
    ],
)
def test_load_upload_rejects_unsupported(data: bytes) -> None:
    with pytest.raises(ImageRejected) as exc:
        load_upload(data)
    assert exc.value.code == "unsupported_format"
    assert "JPEG, PNG or WebP" in exc.value.message


def test_load_upload_rejects_gif_even_when_valid() -> None:
    with pytest.raises(ImageRejected) as exc:
        load_upload(encode(Image.new("RGB", (8, 8)), "GIF"))
    assert exc.value.code == "unsupported_format"


@pytest.mark.parametrize(
    "data",
    [
        b"\xff\xd8\xff\xe0" + b"\x00" * 100,
        b"\x89PNG\r\n\x1a\n" + b"garbage" * 10,
        b"RIFF\x10\x00\x00\x00WEBPVP8 junk",
    ],
)
def test_load_upload_rejects_corrupt(data: bytes) -> None:
    with pytest.raises(ImageRejected) as exc:
        load_upload(data)
    assert exc.value.code == "corrupt"


def test_load_upload_rejects_truncated_jpeg() -> None:
    data = encode(checkerboard(400, 300), "JPEG")
    with pytest.raises(ImageRejected) as exc:
        load_upload(data[: len(data) // 2])
    assert exc.value.code == "corrupt"


def _png_with_size(width: int, height: int) -> bytes:
    data = bytearray(encode(Image.new("RGB", (4, 4)), "PNG"))
    # IHDR chunk starts at byte 8: length(4) type(4) data(13) crc(4)
    ihdr = bytearray(data[16:29])
    ihdr[0:8] = struct.pack(">II", width, height)
    data[16:29] = ihdr
    data[29:33] = struct.pack(">I", zlib.crc32(b"IHDR" + bytes(ihdr)) & 0xFFFFFFFF)
    return bytes(data)


@pytest.mark.parametrize("side", [8_000, 10_000, 20_000])
def test_load_upload_rejects_decompression_bomb(side: int) -> None:
    # 64 MP is over our own limit; 100 MP and 400 MP also trip Pillow's bomb guards.
    with pytest.raises(ImageRejected) as exc:
        load_upload(_png_with_size(side, side))
    assert exc.value.code == "too_large"


def test_load_upload_maps_pillow_bomb_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args, **kwargs):
        raise Image.DecompressionBombError("too big")

    monkeypatch.setattr(prep.PILImage, "open", boom)
    with pytest.raises(ImageRejected) as exc:
        load_upload(encode(Image.new("RGB", (4, 4)), "PNG"))
    assert exc.value.code == "too_large"


def test_load_upload_applies_exif_orientation() -> None:
    src = Image.new("RGB", (200, 100), (0, 0, 0))
    src.paste((255, 0, 0), (0, 0, 100, 100))  # left half red
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90 CW for display
    img = load_upload(encode(src, "JPEG", exif=exif.tobytes(), quality=95))
    assert img.size == (100, 200)
    top = img.getpixel((50, 30))
    bottom = img.getpixel((50, 170))
    assert top[0] > 200 and top[1] < 60
    assert bottom[0] < 60
    assert "exif" not in img.info


def test_load_upload_survives_broken_exif(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(img):
        raise ValueError("bad exif")

    monkeypatch.setattr(prep.ImageOps, "exif_transpose", broken)
    img = load_upload(encode(Image.new("RGB", (20, 10)), "JPEG"))
    assert img.size == (20, 10)


@pytest.mark.parametrize("fmt", ["PNG", "WEBP"])
def test_load_upload_rejects_animated(fmt: str) -> None:
    frames = [Image.new("RGB", (32, 32), c) for c in [(255, 0, 0), (0, 255, 0), (0, 0, 255)]]
    data = encode(frames[0], fmt, save_all=True, append_images=frames[1:], duration=100, loop=0)
    with pytest.raises(ImageRejected) as exc:
        load_upload(data)
    assert exc.value.code == "animated"


# ---------------------------------------------------------------- make_working_copy


def test_make_working_copy_shrinks_long_side() -> None:
    out = make_working_copy(Image.new("RGB", (4000, 3000)))
    assert out.size == (2048, 1536)
    out = make_working_copy(Image.new("RGB", (1000, 3000)), max_side=900)
    assert out.size == (300, 900)


def test_make_working_copy_never_upscales() -> None:
    src = Image.new("L", (800, 600), 9)
    out = make_working_copy(src)
    assert out.size == (800, 600)
    assert out.mode == "RGB"
    assert out is not src


# ---------------------------------------------------------------- check_photo


def test_check_photo_sharp_image_passes() -> None:
    result = check_photo(checkerboard())
    assert result.width == 1200 and result.height == 1000
    assert result.sharpness > prep.SHARPNESS_WARN
    assert 100 < result.brightness < 150
    assert result.issues == []


def test_check_photo_blur_levels() -> None:
    img = checkerboard()
    hard = check_photo(img.filter(ImageFilter.GaussianBlur(6)))
    assert codes(hard) == {"blurry": "hard"}
    assert "too blurry" in hard.issues[0].message
    soft = check_photo(img.filter(ImageFilter.GaussianBlur(2)))
    assert codes(soft) == {"slightly_blurry": "warn"}


def test_check_photo_small_images() -> None:
    assert codes(check_photo(checkerboard(600, 400)))["too_small"] == "hard"
    assert codes(check_photo(checkerboard(1200, 800)))["low_resolution"] == "warn"


@pytest.mark.parametrize(
    ("lo", "hi", "expected"),
    [
        (10, 40, {"too_dark": "hard"}),
        (30, 80, {"dark": "warn"}),
        (220, 252, {"too_bright": "hard"}),
        (190, 240, {"bright": "warn"}),
    ],
)
def test_check_photo_exposure(lo: int, hi: int, expected: dict[str, str]) -> None:
    result = check_photo(checkerboard(lo=lo, hi=hi))
    got = codes(result)
    got.pop("harsh_light", None)
    assert got == expected


def test_check_photo_harsh_light() -> None:
    result = check_photo(checkerboard(lo=0, hi=255))
    assert codes(result) == {"harsh_light": "warn"}


# ---------------------------------------------------------------- to_jev_jpeg


def decode_jev(data: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(data))
    img.load()
    assert img.format == "JPEG"
    assert img.mode == "RGB"
    w, h = img.size
    assert 280 <= w <= 1568 and 280 <= h <= 1568
    assert 78_400 <= w * h <= 2_458_624
    assert "progressive" not in img.info and "progression" not in img.info
    assert "exif" not in img.info
    return img


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        ((4000, 3000), (1568, 1176)),
        ((3000, 4000), (1176, 1568)),
        ((100, 50), (560, 280)),
        ((1000, 40), (1568, 280)),
        ((40, 1000), (280, 1568)),
        ((1568, 1568), (1568, 1568)),
        ((280, 280), (280, 280)),
        ((1569, 280), (1568, 280)),
        ((1, 1), (280, 280)),
        ((800, 600), (800, 600)),
    ],
)
def test_to_jev_jpeg_limits(size: tuple[int, int], expected: tuple[int, int]) -> None:
    img = decode_jev(to_jev_jpeg(Image.new("RGB", size, (200, 30, 30))))
    assert img.size == expected


def test_to_jev_jpeg_pads_extreme_aspect_with_grey() -> None:
    img = decode_jev(to_jev_jpeg(Image.new("RGB", (1000, 40), (255, 0, 0))))
    arr = np.asarray(img).astype(int)
    # 1000x40 -> 1568x63 strip centred in a 1568x280 grey canvas
    assert np.abs(arr[5, 700] - 128).max() <= 3
    assert np.abs(arr[275, 700] - 128).max() <= 3
    assert arr[140, 700, 0] > 200 and arr[140, 700, 1] < 60


def test_to_jev_jpeg_strips_metadata_and_converts_mode() -> None:
    src = Image.new("RGBA", (500, 400), (0, 0, 255, 255))
    src.info["exif"] = b"Exif\x00\x00junk"
    img = decode_jev(to_jev_jpeg(src))
    assert img.size == (500, 400)
    assert img.getexif() == {} or len(img.getexif()) == 0
