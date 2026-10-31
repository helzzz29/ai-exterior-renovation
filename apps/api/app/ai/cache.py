"""Persistent file cache for AI results (JSON decisions/segments, PNG images).

Keys are sha256 hashes of everything that influences a result, so a cache hit is safe to reuse.
This keeps repeated analyses and job retries from spending rate-limited (Gemini free tier) or paid
(Jev) calls.
"""

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger(__name__)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def cache_key(
    step: str,
    model: str,
    prompt_version: str | None,
    image_hashes: list[str],
    payload: Any,
) -> str:
    """Stable key over (step, model, prompt version, input image hashes, question payload)."""
    blob = json.dumps(
        {
            "step": step,
            "model": model,
            "prompt_version": prompt_version,
            "images": image_hashes,
            "payload": payload,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return sha256_bytes(blob.encode("utf-8"))


class FileCache:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _path(self, key: str, suffix: str) -> Path:
        return self.root / key[:2] / f"{key}{suffix}"

    def _write(self, path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def get_json(self, key: str) -> Any | None:
        path = self._path(key, ".json")
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            log.warning("ai_cache_unreadable", path=str(path))
            return None

    def put_json(self, key: str, value: Any) -> None:
        self._write(self._path(key, ".json"), json.dumps(value).encode("utf-8"))

    def get_bytes(self, key: str, suffix: str = ".png") -> bytes | None:
        path = self._path(key, suffix)
        try:
            return path.read_bytes() if path.is_file() else None
        except OSError:
            return None

    def put_bytes(self, key: str, data: bytes, suffix: str = ".png") -> None:
        self._write(self._path(key, suffix), data)
