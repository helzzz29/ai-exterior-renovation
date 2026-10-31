"""Stable SHA-256 fingerprints for staleness checks (independent of any model output)."""

import hashlib
import json
from typing import Any

from pydantic import BaseModel


def _normalise(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _normalise(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {str(k): _normalise(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, list | tuple):
        return [_normalise(v) for v in value]
    if isinstance(value, float):
        return round(value, 6)
    return value


def fingerprint(*parts: Any) -> str:
    payload = json.dumps(_normalise(list(parts)), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
