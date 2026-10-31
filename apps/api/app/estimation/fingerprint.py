"""Input fingerprints for staleness (estimation.md section 8)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel

from app.domain.models import EstimateInputs


def _plain(obj: Any) -> Any:
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    if isinstance(obj, dict):
        return {str(k): _plain(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [_plain(v) for v in obj]
    return obj


def canonical_json(*parts: Any) -> str:
    """Canonical JSON (sorted keys, no whitespace) of pydantic models / plain data."""
    return json.dumps(
        [_plain(p) for p in parts],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def fingerprint(*parts: Any) -> str:
    """Stable SHA-256 hex digest over JSON-serialisable / pydantic inputs."""
    return hashlib.sha256(canonical_json(*parts).encode("utf-8")).hexdigest()


def estimate_fingerprint(inputs: EstimateInputs) -> str:
    """Fingerprint of everything that changes an estimate.

    Covers regions, scale, assignments, the catalogue entries actually used, rate
    overrides, extras, floors and whether the scale is confirmed. Regions, assignments and
    overrides are sorted so that list order does not matter.
    """
    used = sorted({a.material_id for a in inputs.assignments})
    return fingerprint(
        {
            "regions": sorted(inputs.regions, key=lambda r: r.id),
            "scale": inputs.scale,
            "assignments": sorted(
                inputs.assignments, key=lambda a: (a.region_id, a.material_id, a.color or "")
            ),
            "materials": {m: inputs.materials[m] for m in used if m in inputs.materials},
            "overrides": [_plain(o) for o in inputs.overrides],
            "extras": inputs.extras,
            "floors": inputs.floors,
            "scale_confirmed": inputs.scale_confirmed,
        }
    )
