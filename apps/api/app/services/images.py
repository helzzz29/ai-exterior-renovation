"""Persisting and loading images (rows in `images` + bytes in storage)."""

import hashlib
import io

from PIL import Image as PILImage
from PIL.Image import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.api import ImageOut
from app.models import ImageRow
from app.services.image_lane import run_image_work
from app.storage import get_storage, new_key

_FORMATS = {
    "JPEG": ("jpg", "image/jpeg"),
    "PNG": ("png", "image/png"),
    "WEBP": ("webp", "image/webp"),
}


def encode(img: Image, fmt: str = "JPEG") -> bytes:
    buf = io.BytesIO()
    if fmt == "JPEG":
        img.convert("RGB").save(buf, format="JPEG", quality=92)
    else:
        img.save(buf, format=fmt)
    return buf.getvalue()


def sniff(data: bytes) -> tuple[str, str]:
    """(extension, content type) from the file signature; never from the user's filename."""
    if data[:3] == b"\xff\xd8\xff":
        return _FORMATS["JPEG"]
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return _FORMATS["PNG"]
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return _FORMATS["WEBP"]
    return ("bin", "application/octet-stream")


async def store_bytes(
    session: AsyncSession,
    project_id: str,
    kind: str,
    data: bytes,
    width: int,
    height: int,
    content_type: str | None = None,
    ext: str | None = None,
) -> ImageRow:
    if content_type is None or ext is None:
        ext, content_type = sniff(data)
    key = new_key(f"{project_id}/{kind}", ext)
    await get_storage().put(key, data)
    row = ImageRow(
        project_id=project_id,
        kind=kind,
        path=key,
        content_type=content_type,
        width=width,
        height=height,
        sha256=hashlib.sha256(data).hexdigest(),
    )
    session.add(row)
    await session.flush()
    return row


async def encode_off_loop(img: Image, fmt: str = "JPEG") -> bytes:
    return await run_image_work(encode, img, fmt)


async def store_image(
    session: AsyncSession, project_id: str, kind: str, img: Image, fmt: str = "JPEG"
) -> ImageRow:
    data = await encode_off_loop(img, fmt)
    ext, content_type = _FORMATS[fmt]
    return await store_bytes(
        session, project_id, kind, data, img.width, img.height, content_type, ext
    )


async def load_image(row: ImageRow) -> Image:
    data = await get_storage().get(row.path)

    def _open() -> Image:
        img = PILImage.open(io.BytesIO(data))
        img.load()
        return img.convert("RGB")

    return await run_image_work(_open)


def image_url(image_id: str) -> str:
    return f"/api/images/{image_id}"


def image_out(row: ImageRow) -> ImageOut:
    return ImageOut(id=row.id, url=image_url(row.id), width=row.width, height=row.height)
