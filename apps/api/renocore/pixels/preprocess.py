"""Upload decoding, working copies, deterministic photo checks and Jev normalisation."""

import io
import warnings

import cv2
import numpy as np
from PIL import Image as PILImage
from PIL import ImageOps
from PIL.Image import Image

from renocore.pixels.faults import ImageRejected
from renocore.schemas.entities import PhotoCheckResult, PhotoIssue

# ---------------------------------------------------------------- upload limits

MAX_UPLOAD_PIXELS = 60_000_000  # ~60 MP; larger images are treated as decompression bombs
ALLOWED_FORMATS = frozenset({"JPEG", "PNG", "WEBP", "MPO"})  # MPO = multi-picture JPEG

MSG_UNSUPPORTED = "We can only use JPEG, PNG or WebP photos. Please choose a different file."
MSG_CORRUPT = (
    "We couldn't open this photo. The file may be damaged. Please choose a different photo."
)
MSG_TOO_LARGE = (
    "This photo is too large for us to process. Please choose a smaller photo "
    "(under 60 megapixels)."
)
MSG_ANIMATED = "This looks like an animation. Please choose a normal still photo of your house."

# ---------------------------------------------------------------- photo check thresholds

MIN_SHORT_SIDE_HARD = 480
MIN_SHORT_SIDE_WARN = 900
SHARPNESS_ANALYSIS_SIDE = 1024
SHARPNESS_HARD = 15.0
SHARPNESS_WARN = 60.0
BRIGHTNESS_DARK_HARD = 35.0
BRIGHTNESS_DARK_WARN = 60.0
BRIGHTNESS_BRIGHT_HARD = 235.0
BRIGHTNESS_BRIGHT_WARN = 210.0
CLIP_LOW = 5
CLIP_HIGH = 250
CLIPPED_FRACTION_WARN = 0.25

# ---------------------------------------------------------------- Jev limits

JEV_MIN_SIDE = 280
JEV_MAX_SIDE = 1568
JEV_MIN_PIXELS = 78_400
JEV_MAX_PIXELS = 2_458_624
JEV_JPEG_QUALITY = 90
JEV_PAD_GREY = (128, 128, 128)


def _sniff_format(data: bytes) -> str | None:
    if data[:3] == b"\xff\xd8\xff":
        return "JPEG"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "PNG"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "WEBP"
    return None


def _to_rgb(img: Image) -> Image:
    if img.mode == "RGB":
        return img
    if img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        background = PILImage.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    if img.mode.startswith("I;16") or img.mode == "I":
        arr = np.asarray(img.convert("I"), dtype=np.float64)
        top = 65535.0 if arr.max() > 255 else 255.0
        arr8 = np.clip(arr * (255.0 / top), 0, 255).astype(np.uint8)
        return PILImage.fromarray(arr8).convert("RGB")
    return img.convert("RGB")


def load_upload(data: bytes) -> Image:
    """Verify signature/decodability, apply EXIF orientation, return RGB image."""
    sniffed = _sniff_format(data or b"")
    if sniffed is None:
        raise ImageRejected("unsupported_format", MSG_UNSUPPORTED)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", PILImage.DecompressionBombWarning)
            img = PILImage.open(io.BytesIO(data))
            if img.format not in ALLOWED_FORMATS:
                raise ImageRejected("unsupported_format", MSG_UNSUPPORTED)
            if img.width * img.height > MAX_UPLOAD_PIXELS:
                raise ImageRejected("too_large", MSG_TOO_LARGE)
            if img.format in ("PNG", "WEBP") and getattr(img, "n_frames", 1) > 1:
                raise ImageRejected("animated", MSG_ANIMATED)
            img.load()
    except ImageRejected:
        raise
    except (PILImage.DecompressionBombError, PILImage.DecompressionBombWarning) as exc:
        raise ImageRejected("too_large", MSG_TOO_LARGE) from exc
    except Exception as exc:  # any decoder failure means the file is unusable
        raise ImageRejected("corrupt", MSG_CORRUPT) from exc
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:  # broken EXIF: keep the pixels as stored
        pass
    out = _to_rgb(img)
    out.info.pop("exif", None)
    return out


def make_working_copy(img: Image, max_side: int = 2048) -> Image:
    """Shrink (never enlarge) so the longest side is at most `max_side`."""
    img = _to_rgb(img)
    w, h = img.size
    longest = max(w, h)
    if longest <= max_side:
        return img.copy()
    scale = max_side / longest
    size = (max(1, min(max_side, round(w * scale))), max(1, min(max_side, round(h * scale))))
    return img.resize(size, PILImage.Resampling.LANCZOS)


# ---------------------------------------------------------------- photo check


def _analysis_gray(img: Image) -> np.ndarray:
    gray = img.convert("L")
    w, h = gray.size
    longest = max(w, h)
    if longest > SHARPNESS_ANALYSIS_SIDE:
        scale = SHARPNESS_ANALYSIS_SIDE / longest
        gray = gray.resize(
            (max(1, round(w * scale)), max(1, round(h * scale))), PILImage.Resampling.BILINEAR
        )
    return np.asarray(gray, dtype=np.uint8)


def check_photo(img: Image) -> PhotoCheckResult:
    """Resolution, sharpness (Laplacian variance), exposure checks with user-facing messages."""
    width, height = img.size
    gray = _analysis_gray(img)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brightness = float(np.asarray(img.convert("L"), dtype=np.float64).mean())
    clipped = float(np.mean((gray <= CLIP_LOW) | (gray >= CLIP_HIGH)))

    issues: list[PhotoIssue] = []
    short = min(width, height)
    if short < MIN_SHORT_SIDE_HARD:
        issues.append(
            PhotoIssue(
                code="too_small",
                severity="hard",
                message=(
                    "This photo is too small to measure. Please use the original photo from "
                    "your phone camera, not a screenshot or a photo sent over chat."
                ),
            )
        )
    elif short < MIN_SHORT_SIDE_WARN:
        issues.append(
            PhotoIssue(
                code="low_resolution",
                severity="warn",
                message=(
                    "This photo is a bit small, so sizes may be less accurate. If you can, "
                    "use the original photo from your phone camera."
                ),
            )
        )

    if sharpness < SHARPNESS_HARD:
        issues.append(
            PhotoIssue(
                code="blurry",
                severity="hard",
                message=(
                    "This photo is too blurry to measure. Hold the phone steady and try again "
                    "in daylight."
                ),
            )
        )
    elif sharpness < SHARPNESS_WARN:
        issues.append(
            PhotoIssue(
                code="slightly_blurry",
                severity="warn",
                message=(
                    "This photo looks a little blurry, so some details may be missed. A "
                    "steadier, sharper photo will give better results."
                ),
            )
        )

    if brightness < BRIGHTNESS_DARK_HARD:
        issues.append(
            PhotoIssue(
                code="too_dark",
                severity="hard",
                message=(
                    "This photo is too dark to see the house clearly. Please take it again in "
                    "daylight."
                ),
            )
        )
    elif brightness < BRIGHTNESS_DARK_WARN:
        issues.append(
            PhotoIssue(
                code="dark",
                severity="warn",
                message=(
                    "This photo is quite dark, so some parts may be hard to see. A photo taken "
                    "in daylight will work better."
                ),
            )
        )
    elif brightness > BRIGHTNESS_BRIGHT_HARD:
        issues.append(
            PhotoIssue(
                code="too_bright",
                severity="hard",
                message=(
                    "This photo is too bright to see the house clearly. Avoid pointing the "
                    "camera towards the sun and try again."
                ),
            )
        )
    elif brightness > BRIGHTNESS_BRIGHT_WARN:
        issues.append(
            PhotoIssue(
                code="bright",
                severity="warn",
                message=(
                    "This photo is very bright, so some parts may look washed out. Try a time "
                    "of day when the sun isn't shining straight at the camera."
                ),
            )
        )

    if clipped > CLIPPED_FRACTION_WARN:
        issues.append(
            PhotoIssue(
                code="harsh_light",
                severity="warn",
                message=(
                    "Parts of this photo are in very strong light or deep shadow, so some "
                    "details may be lost. A photo on a cloudy day or in softer light works best."
                ),
            )
        )

    return PhotoCheckResult(
        width=width,
        height=height,
        sharpness=round(sharpness, 2),
        brightness=round(brightness, 2),
        issues=issues,
    )


# ---------------------------------------------------------------- Jev normalisation


def _jev_scaled_size(w: int, h: int) -> tuple[int, int]:
    longest, short = max(w, h), min(w, h)
    scale = min(1.0, JEV_MAX_SIDE / longest)
    if short * scale < JEV_MIN_SIDE:
        scale = min(JEV_MIN_SIDE / short, JEV_MAX_SIDE / longest)
    nw = max(1, min(JEV_MAX_SIDE, round(w * scale)))
    nh = max(1, min(JEV_MAX_SIDE, round(h * scale)))
    return nw, nh


def to_jev_jpeg(img: Image) -> bytes:
    """Normalise for Jev: each side 280-1568 px (shrink, pad/upscale), baseline JPEG q90."""
    rgb = _to_rgb(img)
    w, h = rgb.size
    nw, nh = _jev_scaled_size(w, h)
    if (nw, nh) != (w, h):
        rgb = rgb.resize((nw, nh), PILImage.Resampling.LANCZOS)
    cw, ch = max(nw, JEV_MIN_SIDE), max(nh, JEV_MIN_SIDE)
    # Fresh canvas: drops all metadata (EXIF, ICC, comments) and pads with neutral grey.
    canvas = PILImage.new("RGB", (cw, ch), JEV_PAD_GREY)
    canvas.paste(rgb, ((cw - nw) // 2, (ch - nh) // 2))

    assert JEV_MIN_SIDE <= cw <= JEV_MAX_SIDE and JEV_MIN_SIDE <= ch <= JEV_MAX_SIDE
    assert JEV_MIN_PIXELS <= cw * ch <= JEV_MAX_PIXELS

    buf = io.BytesIO()
    canvas.save(buf, format="JPEG", quality=JEV_JPEG_QUALITY, progressive=False, optimize=False)
    return buf.getvalue()
