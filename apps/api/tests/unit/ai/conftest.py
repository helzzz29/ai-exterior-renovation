"""Shared fakes for AI tests: simple imaging stand-ins, a fake Jev SDK and a fake Gemini SDK."""

import base64
import io
import json
from pathlib import Path
from typing import Any

import pytest
from google.genai import types
from PIL import Image as PILImage
from PIL import ImageDraw
from typesafe_sdk import Box, Choice, Noul, Score, SystemOneResponse

import app.imaging as imaging
from app.ai.cache import FileCache
from app.ai.gemini_client import GeminiClient
from app.ai.jev_client import JevClient
from app.ai.tracing import Tracer
from app.config import Settings
from app.domain.ai import AICallRecord
from app.domain.models import BoxPx, Material, Region, SegmentCandidate

# ---------------------------------------------------------------- fake imaging (stubs)


def _jpeg(img: Any) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _poly_box(polygon: list) -> BoxPx:
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    return BoxPx(x0=min(xs), y0=min(ys), x1=max(xs), y1=max(ys))


def _iou(a: BoxPx, b: BoxPx) -> float:
    ix = max(0.0, min(a.x1, b.x1) - max(a.x0, b.x0))
    iy = max(0.0, min(a.y1, b.y1) - max(a.y0, b.y0))
    inter = ix * iy
    union = (a.x1 - a.x0) * (a.y1 - a.y0) + (b.x1 - b.x0) * (b.y1 - b.y0) - inter
    return inter / union if union > 0 else 0.0


def _segments_to_candidates(segments: list, width: int, height: int) -> list[SegmentCandidate]:
    out = []
    for s in segments:
        y0, x0, y1, x1 = s.box_2d
        box = BoxPx(
            x0=x0 * width / 1000, y0=y0 * height / 1000, x1=x1 * width / 1000, y1=y1 * height / 1000
        )
        poly = [(box.x0, box.y0), (box.x1, box.y0), (box.x1, box.y1), (box.x0, box.y1)]
        out.append(SegmentCandidate(label_hint=s.label, polygon=poly, box=box))
    return out


def _region_crop(img: Any, polygon: list, pad: float = 0.25, outline: bool = True) -> Any:
    b = _poly_box(polygon)
    return img.crop(
        (int(b.x0), int(b.y0), max(int(b.x1), int(b.x0) + 1), max(int(b.y1), int(b.y0) + 1))
    )


def _zone_map(img: Any, zones: list) -> Any:
    out = img.convert("RGB").point(lambda v: v // 2)
    draw = ImageDraw.Draw(out)
    for polys, rgb in zones:
        for poly in polys:
            draw.polygon(poly, fill=tuple(rgb))
    return out


def _composite(
    original: Any, generated: Any, include: list, exclude: list, feather_px: int = 3
) -> Any:
    return generated.convert("RGB").resize(original.size)


FAKE_IMAGING = {
    "to_jev_jpeg": _jpeg,
    "segments_to_candidates": _segments_to_candidates,
    "region_crop": _region_crop,
    "zone_map": _zone_map,
    "composite": _composite,
    "fraction_box_to_px": lambda box, w, h: BoxPx(
        x0=box.left * w, y0=box.top * h, x1=box.right * w, y1=box.bottom * h
    ),
    "polygon_box": _poly_box,
    "box_polygon": lambda b: [(b.x0, b.y0), (b.x1, b.y0), (b.x1, b.y1), (b.x0, b.y1)],
    "box_iou": _iou,
    "polygon_area_px": lambda poly: (
        abs(
            sum(
                poly[i][0] * poly[(i + 1) % len(poly)][1]
                - poly[(i + 1) % len(poly)][0] * poly[i][1]
                for i in range(len(poly))
            )
        )
        / 2
    ),
}


@pytest.fixture(autouse=True)
def fake_imaging(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, fn in FAKE_IMAGING.items():
        monkeypatch.setattr(imaging, name, fn)


# ---------------------------------------------------------------- domain factories


def make_photo(w: int = 400, h: int = 300, color: tuple = (180, 170, 150)) -> Any:
    return PILImage.new("RGB", (w, h), color)


def rect(x0: float, y0: float, x1: float, y1: float) -> list[tuple[float, float]]:
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def make_region(rid: str, label: str, box: tuple = (10, 10, 100, 100), **kw: Any) -> Region:
    return Region(id=rid, label=label, polygon=rect(*box), **kw)


def make_material(mid: str, labels: list[str], **kw: Any) -> Material:
    base: dict[str, Any] = dict(
        id=mid,
        name=kw.pop("name", mid.replace("_", " ").title()),
        category="paint",
        description=kw.pop("description", f"{mid} finish"),
        applicable_labels=labels,
        pricing_unit="litre",
        measure_basis="area",
        wastage_pct=5,
        material_rate=100,
        labour_rate=10,
        swatch=f"{mid}.png",
        weather_resistance="high",
        durability="8-10 years",
        maintenance="Wash once a year.",
    )
    base.update(kw)
    return Material(**base)


@pytest.fixture
def materials() -> dict[str, Material]:
    return {
        "paint": make_material(
            "paint",
            ["wall", "parapet", "pillar"],
            colorable=True,
            default_color="#eeddcc",
            name="Beige texture paint",
        ),
        "stone": make_material("stone", ["wall", "pillar"], name="Natural stone cladding"),
        "lime": make_material(
            "lime",
            ["wall"],
            weather_resistance="low",
            name="Lime wash",
            maintenance="Needs frequent maintenance in rain.",
        ),
        "glass": make_material("glass", ["railing"], name="Toughened glass railing"),
    }


class Recorder:
    def __init__(self) -> None:
        self.calls: list[AICallRecord] = []

    async def record(self, call: AICallRecord) -> None:
        self.calls.append(call)


@pytest.fixture
def recorder() -> Recorder:
    return Recorder()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        ai_provider="fake",
        storage_root=tmp_path / "data",
        seed_dir=tmp_path / "seed",
        gemini_api_key="",
        jev_api_key="",
    )


# ---------------------------------------------------------------- fake Jev SDK


def default_answer(q: Any) -> dict[str, Any]:
    if isinstance(q, Noul):
        return {"type": "noul", "noul": 0.9}
    if isinstance(q, Choice):
        keys = list(q.criteria)
        probs = {k: (0.8 if i == 0 else 0.2 / max(len(keys) - 1, 1)) for i, k in enumerate(keys)}
        return {"type": "choice", "choice": keys[0], "confidence": 0.8, "probabilities": probs}
    if isinstance(q, Score):
        n = len(q.criteria)
        return {
            "type": "score",
            "score": 3.0,
            "confidence": 0.7,
            "legend": {str(i): f"l{i}" for i in range(n)},
            "probabilities": {str(i): 1.0 / n for i in range(n)},
        }
    if isinstance(q, Box):
        return {
            "type": "box",
            "box": {"top": 0.6, "bottom": 0.9, "left": 0.4, "right": 0.6},
            "confidence": 0.85,
        }
    raise TypeError(q)


def sdk_response(answers: dict[str, dict], input_tokens: int = 1000) -> SystemOneResponse:
    return SystemOneResponse.model_validate_json(
        json.dumps(
            {
                "model": "jev-latest",
                "usage": {"input_tokens": input_tokens, "output_tokens": 3},
                "answers": answers,
            }
        )
    )


class FakeJevSDK:
    """Stands in for AsyncTypeSafeClient: default answers per question, with overrides."""

    def __init__(self, overrides: dict[str, dict] | None = None) -> None:
        self.overrides = overrides or {}
        self.calls: list[tuple[Any, dict]] = []

    async def system_one(self, state: Any, questions: dict) -> SystemOneResponse:
        self.calls.append((state, questions))
        answers = {}
        for name, q in questions.items():
            answers[name] = {**default_answer(q), **self.overrides.get(name, {})}
        return sdk_response(answers)

    async def aclose(self) -> None:
        pass


def make_jev(
    sdk: Any, recorder: Recorder | None = None, cache: FileCache | None = None
) -> JevClient:
    return JevClient(
        api_key="k",
        model="jev-latest",
        max_concurrency=2,
        tracer=Tracer(recorder),
        cache=cache,
        client=sdk,
    )


# ---------------------------------------------------------------- fake Gemini SDK


def text_response(text: str) -> types.GenerateContentResponse:
    return types.GenerateContentResponse(
        candidates=[
            types.Candidate(content=types.Content(role="model", parts=[types.Part(text=text)]))
        ],
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=100, candidates_token_count=50
        ),
        response_id="resp-1",
    )


def image_response(png: bytes, text: str | None = None) -> types.GenerateContentResponse:
    parts = []
    if text:
        parts.append(types.Part(text=text))
    parts.append(types.Part(inline_data=types.Blob(data=png, mime_type="image/png")))
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=parts))],
        response_id="resp-img",
    )


class FakeGeminiSDK:
    """Stands in for genai.Client: `aio.models.generate_content` returns/raises scripted items."""

    def __init__(self, script: list[Any]) -> None:
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []
        self.aio = self
        self.models = self

    async def generate_content(self, *, model: str, contents: list, config: Any) -> Any:
        self.calls.append({"model": model, "contents": contents, "config": config})
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def no_wait(_state: Any) -> float:
    return 0.0


def make_gemini(sdk: Any, recorder: Recorder | None = None) -> GeminiClient:
    return GeminiClient(
        api_key="k", max_concurrency=1, tracer=Tracer(recorder), client=sdk, wait=no_wait
    )


def png_bytes(w: int = 8, h: int = 8, color: tuple = (255, 255, 255)) -> bytes:
    buf = io.BytesIO()
    PILImage.new("RGB", (w, h), color).save(buf, format="PNG")
    return buf.getvalue()


MASK_JSON = "data:image/png;base64," + base64.b64encode(png_bytes()).decode()
