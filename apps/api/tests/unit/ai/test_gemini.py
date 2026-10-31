"""Gemini calls C2 (segmentation) and C5 (redesign): parts order, config, parsing, retries."""

import base64
import json

import httpx
import pytest
from google.genai import errors, types
from tenacity import RetryCallState

from app.ai import gemini_client
from app.ai.cache import FileCache
from app.ai.gemini_client import GeminiClient, backoff_wait, is_retryable, retry_delay_seconds
from app.ai.media import decode_image
from app.ai.prompts import load_prompt
from app.ai.steps import render, segment
from app.ai.tracing import Tracer
from app.domain.models import Zone
from tests.unit.ai.conftest import (
    FakeGeminiSDK,
    image_response,
    make_gemini,
    make_photo,
    png_bytes,
    text_response,
)

MASK = "data:image/png;base64," + base64.b64encode(png_bytes()).decode()


def seg_json(*items: tuple[str, list[int]]) -> str:
    return json.dumps([{"label": label, "box_2d": box, "mask": MASK} for label, box in items])


def poly_json(*items: tuple[str, list[list[int]]]) -> str:
    return json.dumps(
        [{"label": label, "box_2d": [0, 0, 1, 1], "polygon": pts} for label, pts in items]
    )


SQUARE = [[100, 50], [100, 950], [900, 950], [900, 50]]
POLY_GOOD = poly_json(
    ("wall", SQUARE),
    ("window", [[300, 200], [300, 350], [500, 350], [500, 200]]),
    ("tree", SQUARE),
)

MASK_GOOD = seg_json(
    ("wall", [100, 50, 900, 950]),
    ("window", [300, 200, 500, 350]),
    ("Column", [100, 50, 900, 100]),
    ("tree", [0, 0, 100, 100]),
)


def quota_error(delay: str | None = "7s") -> errors.ClientError:
    details = [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": delay}]
    return errors.ClientError(
        429,
        {
            "error": {
                "code": 429,
                "status": "RESOURCE_EXHAUSTED",
                "message": "quota",
                "details": details,
            }
        },
    )


@pytest.fixture(autouse=True)
def reset_thinking(monkeypatch):
    monkeypatch.setattr(segment, "_thinking_rejected", set())
    monkeypatch.setenv(segment.SEGMENT_MODE_ENV, "polygon")  # label-map mode: test_labelmap.py


# ---------------------------------------------------------------- C2 request


def test_c2_parts_and_config_snapshot():
    assert segment.SEGMENT_OUTPUT_MODE == "labelmap"
    assert segment.output_mode() == "polygon"  # env override
    contents = segment.build_contents(b"JPEG", mode="polygon")
    assert len(contents) == 2
    assert contents[0].inline_data.data == b"JPEG"
    assert contents[0].inline_data.mime_type == "image/jpeg"
    assert contents[1] == load_prompt("segment_v2")
    config = segment.build_config("gemini-3.8-flash", "polygon")
    assert config.temperature == 0
    assert config.response_mime_type == "application/json"
    assert config.response_schema is None  # validated with pydantic afterwards
    assert config.max_output_tokens == 8192
    assert config.thinking_config.thinking_level == types.ThinkingLevel.LOW
    assert segment.build_config("m", "mask").max_output_tokens == 32768
    assert segment.build_contents(b"J", mode="mask")[1] == load_prompt("segment_v1")
    reask = segment.build_contents(b"JPEG", "bad JSON", mode="polygon")
    assert reask[1].startswith(load_prompt("segment_v2"))
    assert "Your previous answer could not be used: bad JSON" in reask[1]


def test_output_mode_env(monkeypatch):
    monkeypatch.setenv(segment.SEGMENT_MODE_ENV, "MASK")
    assert segment.output_mode() == "mask"
    monkeypatch.setenv(segment.SEGMENT_MODE_ENV, "boxes")
    with pytest.raises(ValueError, match="mask"):
        segment.output_mode()


@pytest.mark.parametrize(("name", "fmt"), [("segment_v1", "mask"), ("segment_v2", "polygon")])
def test_segment_prompt_content(name, fmt):
    prompt = load_prompt(name)
    assert fmt in prompt
    for word in (
        "wall, window, door, balcony, pillar, parapet, railing, gate, roof_edge",
        "box_2d",
        "0-1000",
        "SEPARATE",
        "sky",
        "vegetation",
        "vehicles",
        "neighbouring building",
    ):
        assert word in prompt


def test_segment_v2_prompt_rules():
    prompt = load_prompt("segment_v2")
    for phrase in (
        "each separate wall face",
        "follow the building edge tightly",
        "sloped roof itself is not roof_edge",
        "low wall along the top of a flat roof",
        "4 to 16 points",
    ):
        assert phrase in prompt


# ---------------------------------------------------------------- C2 validation


@pytest.mark.parametrize(
    ("text", "error"),
    [
        (None, "empty"),
        ("not json", "not valid JSON"),
        ('{"a": 1}', "JSON list"),
        ("[1]", "not a JSON object"),
        ('[{"box_2d": [1,2,3,4], "mask": "x"}]', "no label"),
        ('[{"label": "wall", "box_2d": [1,2,3], "mask": "x"}]', "four numbers"),
        (seg_json(("wall", [0, 0, 1001, 10])), "out of the 0-1000 range"),
        (seg_json(("wall", [500, 0, 400, 10])), "y0 < y1"),
        (seg_json(("window", [0, 0, 10, 10])), "no wall"),
    ],
)
def test_validate_errors(text, error):
    with pytest.raises(ValueError, match=error):
        segment.validate(text, "mask")


def test_validate_normalises_and_drops():
    out = segment.validate("```json\n" + MASK_GOOD + "\n```", "mask")
    assert [s.label for s in out] == ["wall", "window", "pillar"]  # tree dropped
    wrapped = segment.validate(json.dumps({"items": json.loads(MASK_GOOD)}), "mask")
    assert len(wrapped) == 3


def test_bad_mask_is_blanked_not_reasked():
    text = json.dumps(
        [
            {"label": "wall", "box_2d": [0, 0, 10, 10], "mask": "@@notpng"},
            {"label": "wall", "box_2d": [0, 0, 10, 10]},
        ]
    )
    assert [s.mask for s in segment.validate(text, "mask")] == ["", ""]


@pytest.mark.parametrize(
    ("text", "error"),
    [
        ('[{"label": "wall"}]', "list of"),
        ('[{"label": "wall", "polygon": [[1, 2, 3]]}]', "pairs"),
        ('[{"label": "wall", "polygon": [["a", 1]]}]', "pairs"),
        (poly_json(("window", SQUARE)), "no wall"),
        (poly_json(("wall", [[1, 1], [2, 2]])), "no wall"),
    ],
)
def test_validate_polygon_errors(text, error):
    with pytest.raises(ValueError, match=error):
        segment.validate(text, "polygon")


def test_validate_polygon_clamps_and_boxes():
    text = poly_json(("Main Wall", [[-20, 50], [100, 1200], [900, 950]]), ("sky", SQUARE))
    (seg,) = segment.validate(text, "polygon")
    assert seg.label == "wall"
    assert seg.polygon == [[0, 50], [100, 1000], [900, 950]]
    assert seg.box_2d == [0, 50, 900, 1000]


def test_polygons_to_candidates():
    segs = segment.validate(
        poly_json(("wall", SQUARE), ("window", [[0, 0], [0, 10], [10, 10], [10, 0]])), "polygon"
    )
    cands = segment.polygons_to_candidates(segs, 2000, 1000)
    assert len(cands) == 1  # tiny window dropped (< 0.2% of the image)
    assert cands[0].polygon == [(100, 100), (1900, 100), (1900, 900), (100, 900)]
    assert (cands[0].box.x0, cands[0].box.y1) == (100, 900)


@pytest.mark.parametrize(
    ("raw", "label"),
    [("Main Wall", "wall"), ("roof-edge", "roof_edge"), ("fascia", "roof_edge"), ("sky", None)],
)
def test_normalise_label(raw, label):
    assert segment.normalise_label(raw) == label


# ---------------------------------------------------------------- C2 run


async def test_polygon_mode_default_success_and_cache(tmp_path, recorder):
    sdk = FakeGeminiSDK([text_response(POLY_GOOD)])
    gem = make_gemini(sdk, recorder)
    cache = FileCache(tmp_path)
    photo = make_photo(1000, 500)
    cands = await segment.run(gem, cache, "gemini-3.8-flash", photo)
    assert [c.label_hint for c in cands] == ["wall", "window"]
    assert cands[0].polygon[0] == (50, 50)
    assert recorder.calls[0].prompt_version == "segment_v2"
    again = await segment.run(gem, cache, "gemini-3.8-flash", photo)
    assert len(sdk.calls) == 1 and len(again) == 2 and recorder.calls[-1].cached
    sdk.script.append(text_response(MASK_GOOD))  # mask mode is a separate cache entry
    await segment.run(gem, cache, "gemini-3.8-flash", photo, mode="mask")
    assert len(sdk.calls) == 2


async def test_mask_mode_success_and_cache(tmp_path, recorder):
    sdk = FakeGeminiSDK([text_response(MASK_GOOD)])
    gem = make_gemini(sdk, recorder)
    cache = FileCache(tmp_path)
    photo = make_photo(1000, 500)
    cands = await segment.run(gem, cache, "gemini-3.8-flash", photo, mode="mask")
    assert [c.label_hint for c in cands] == ["wall", "window", "pillar"]
    assert cands[0].box.x0 == 50 and cands[0].box.y0 == 50
    assert sdk.calls[0]["model"] == "gemini-3.8-flash"
    rec = recorder.calls[0]
    assert rec.step == "C2" and rec.provider == "gemini" and rec.prompt_version == "segment_v1"
    assert rec.input_tokens == 100 and rec.output_tokens == 50 and rec.request_id == "resp-1"
    assert "mask" not in json.dumps(rec.output)
    again = await segment.run(gem, cache, "gemini-3.8-flash", photo, mode="mask")
    assert len(sdk.calls) == 1 and len(again) == 3
    assert recorder.calls[-1].cached is True


async def test_malformed_json_triggers_exactly_one_reask(recorder):
    sdk = FakeGeminiSDK([text_response("{oops"), text_response(POLY_GOOD)])
    out = await segment.run(make_gemini(sdk, recorder), None, "m", make_photo())
    assert len(sdk.calls) == 2 and len(out) == 2
    second_prompt = sdk.calls[1]["contents"][1]
    assert "not valid JSON" in second_prompt
    assert recorder.calls[0].error.startswith("invalid output (attempt 1)")
    assert recorder.calls[1].error is None


async def test_second_failure_raises_clear_error():
    sdk = FakeGeminiSDK([text_response("{oops"), text_response(poly_json(("door", SQUARE)))])
    with pytest.raises(segment.SegmentationError, match="unusable output twice: no wall"):
        await segment.run(make_gemini(sdk), None, "m", make_photo())
    assert len(sdk.calls) == 2


async def test_truncated_or_empty_output_is_reasked(recorder):
    cut = text_response(POLY_GOOD[:40])
    cut.candidates[0].finish_reason = types.FinishReason.MAX_TOKENS
    sdk = FakeGeminiSDK([cut, text_response(POLY_GOOD)])
    out = await segment.run(make_gemini(sdk, recorder), None, "m", make_photo())
    assert len(out) == 2
    assert "cut off" in sdk.calls[1]["contents"][1]
    sdk = FakeGeminiSDK([text_response("  "), text_response("")])
    with pytest.raises(segment.SegmentationError, match="empty"):
        await segment.run(make_gemini(sdk), None, "m", make_photo())


async def test_thinking_rejection_falls_back_once():
    reject = errors.ClientError(
        400,
        {
            "error": {
                "code": 400,
                "status": "INVALID_ARGUMENT",
                "message": "thinking_level is not supported",
            }
        },
    )
    sdk = FakeGeminiSDK([reject, text_response(POLY_GOOD), text_response(POLY_GOOD)])
    gem = make_gemini(sdk)
    await segment.run(gem, None, "m", make_photo())
    assert sdk.calls[0]["config"].thinking_config is not None
    assert sdk.calls[1]["config"].thinking_config is None
    await segment.run(gem, None, "m", make_photo())
    assert sdk.calls[2]["config"].thinking_config is None  # remembered


async def test_other_client_error_propagates():
    sdk = FakeGeminiSDK([errors.ClientError(403, {"error": {"message": "denied"}})])
    with pytest.raises(errors.ClientError):
        await segment.run(make_gemini(sdk), None, "m", make_photo())


# ---------------------------------------------------------------- retries


async def test_429_then_success_retries_once(recorder):
    sdk = FakeGeminiSDK([quota_error(), text_response(POLY_GOOD)])
    await segment.run(make_gemini(sdk, recorder), None, "m", make_photo())
    assert len(sdk.calls) == 2
    assert recorder.calls[0].attempts == 2


async def test_gives_up_after_five_attempts(recorder):
    sdk = FakeGeminiSDK([errors.ServerError(503, {"error": {"message": "busy"}})] * 6)
    with pytest.raises(errors.ServerError):
        await segment.run(make_gemini(sdk, recorder), None, "m", make_photo())
    assert len(sdk.calls) == 5
    assert recorder.calls[0].attempts == 5 and "503" in recorder.calls[0].error


async def test_timeout_is_retried():
    sdk = FakeGeminiSDK([httpx.ReadTimeout("slow"), text_response(POLY_GOOD)])
    await segment.run(make_gemini(sdk), None, "m", make_photo())
    assert len(sdk.calls) == 2


@pytest.mark.parametrize(
    ("exc", "retry"),
    [
        (errors.ClientError(429, {}), True),
        (errors.ServerError(500, {}), True),
        (errors.ServerError(503, {}), True),
        (errors.ServerError(504, {}), True),
        (errors.ServerError(501, {}), False),
        (errors.ClientError(400, {}), False),
        (TimeoutError(), True),
        (ValueError(), False),
    ],
)
def test_is_retryable(exc, retry):
    assert is_retryable(exc) is retry


def test_retry_delay_and_backoff():
    assert retry_delay_seconds(quota_error("7s")) == 7.0
    assert retry_delay_seconds(quota_error("soon")) is None
    assert retry_delay_seconds(errors.ServerError(500, {})) is None
    assert retry_delay_seconds(errors.ClientError(429, [{"error": {"details": "x"}}])) is None

    def state(exc, n):
        s = RetryCallState(retry_object=None, fn=None, args=(), kwargs={})
        s.attempt_number = n
        s.set_exception((type(exc), exc, None))
        return s

    assert 7.0 <= backoff_wait(state(quota_error("7s"), 1)) <= 8.0
    assert 1.0 <= backoff_wait(state(errors.ServerError(500, {}), 1)) <= 2.0
    assert backoff_wait(state(errors.ServerError(500, {}), 20)) <= gemini_client.BACKOFF_MAX_S


def test_missing_gemini_key():
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        _ = GeminiClient("", 1, Tracer()).client
    assert GeminiClient("abc", 1, Tracer()).client is not None


# ---------------------------------------------------------------- C5


@pytest.fixture
def zones():
    return [
        Zone(region_ids=["a"], material_id="stone", color_name="red", rgb=(255, 0, 0)),
        Zone(region_ids=["b"], material_id="paint@123456", color_name="blue", rgb=(0, 0, 255)),
    ]


@pytest.fixture
def render_materials(materials):
    out = dict(materials)
    out["paint@123456"] = materials["paint"].model_copy(
        update={"id": "paint@123456", "default_color": "#123456"}
    )
    return out


def test_c5_prompt(zones, render_materials):
    prompt = render.build_prompt(zones, render_materials, "  Make it warm ", ["Fix A", "Fix B"])
    assert "- red zone -> Natural stone cladding (sample: image 3). stone finish" in prompt
    assert "- blue zone -> Beige texture paint in colour #123456 (sample: image 4)" in prompt
    assert "The homeowner also asked: Make it warm" in prompt
    assert "- Fix: Fix A\n- Fix: Fix B" in prompt
    for word in (
        "geometry",
        "camera",
        "window",
        "door",
        "roofline",
        "sky",
        "ground",
        "surroundings",
        "lighting",
        "photorealistic",
        "zone map",
    ):
        assert word in prompt.lower()
    plain = render.build_prompt(zones, render_materials, None, None)
    assert "also asked" not in plain and "Fix" not in plain and "$" not in plain


@pytest.mark.parametrize(
    ("w", "h", "ratio"),
    [
        (1000, 1000, "1:1"),
        (1600, 1200, "4:3"),
        (1200, 1600, "3:4"),
        (1920, 1080, "16:9"),
        (1500, 1000, "3:2"),
        (1000, 2000, "9:16"),
    ],
)
def test_c5_config(w, h, ratio):
    config = render.build_config(w, h)
    assert config.response_modalities == ["TEXT", "IMAGE"]
    assert config.image_config.aspect_ratio == ratio
    assert config.image_config.image_size == "2K"


def test_c5_parts_order():
    parts = render.build_contents(b"PHOTO", b"ZONES", [b"S1", b"S2"], "PROMPT")
    assert [(p.inline_data.data, p.inline_data.mime_type) for p in parts[:4]] == [
        (b"PHOTO", "image/jpeg"),
        (b"ZONES", "image/png"),
        (b"S1", "image/png"),
        (b"S2", "image/png"),
    ]
    assert parts[4] == "PROMPT"


def test_extract_image_skips_thoughts():
    thought = types.Part(inline_data=types.Blob(data=b"T", mime_type="image/png"), thought=True)
    resp = types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(
                    parts=[
                        types.Part(text="here"),
                        thought,
                        types.Part(inline_data=types.Blob(data=b"IMG", mime_type="image/png")),
                    ]
                )
            )
        ]
    )
    assert render.extract_image(resp) == (b"IMG", "here")
    assert render.extract_image(text_response("no")) == (None, "no")
    assert render.extract_image(types.GenerateContentResponse()) == (None, None)


async def test_c5_generate_and_cache(tmp_path, zones, render_materials, recorder):
    out_png = png_bytes(64, 48, (10, 200, 30))
    sdk = FakeGeminiSDK([image_response(out_png)])
    gem = make_gemini(sdk, recorder)
    cache = FileCache(tmp_path / "c")
    photo, zmap = make_photo(640, 480), make_photo(640, 480, (0, 0, 0))
    args = (
        gem,
        cache,
        "gemini-nano-banana-2.1",
        tmp_path / "seed",
        photo,
        zmap,
        zones,
        render_materials,
    )
    img = await render.generate(*args, "note", None)
    assert img.size == (64, 48) and img.getpixel((0, 0)) == (10, 200, 30)
    call = sdk.calls[0]
    assert call["model"] == "gemini-nano-banana-2.1"
    assert len(call["contents"]) == 5  # photo, zone map, 2 swatches, prompt
    assert decode_image(call["contents"][3].inline_data.data).getpixel((5, 5)) == (18, 52, 86)
    assert call["config"].image_config.aspect_ratio == "4:3"
    assert recorder.calls[0].step == "C5" and recorder.calls[0].request_id == "resp-img"
    # cache hit for same inputs; attempt index and notes change the key
    again = await render.generate(*args, "note", None)
    assert again.getpixel((0, 0)) == (10, 200, 30) and len(sdk.calls) == 1
    assert recorder.calls[-1].cached
    sdk.script.append(image_response(out_png))
    await render.generate(*args, "note", None, attempt=1)
    sdk.script.append(image_response(out_png))
    await render.generate(*args, "note", ["Fix it"], attempt=1)
    assert len(sdk.calls) == 3
    # an explicit redo (new cache salt) regenerates; the same salt is served from cache
    sdk.script.append(image_response(out_png))
    await render.generate(*args, "note", None, cache_salt="render-2")
    await render.generate(*args, "note", None, cache_salt="render-2")
    assert len(sdk.calls) == 4


async def test_c5_no_image_reasks_then_fails(tmp_path, zones, render_materials):
    sdk = FakeGeminiSDK([text_response("I can't"), text_response("still no")])
    with pytest.raises(render.RenderError, match="still no"):
        await render.generate(
            make_gemini(sdk),
            None,
            "m",
            tmp_path,
            make_photo(),
            make_photo(),
            zones,
            render_materials,
            None,
            None,
        )
    assert len(sdk.calls) == 2
    assert sdk.calls[1]["contents"][-1].endswith("Return the edited photo as an image.")


async def test_c5_no_image_then_image(tmp_path, zones, render_materials):
    sdk = FakeGeminiSDK([text_response("hmm"), image_response(png_bytes())])
    img = await render.generate(
        make_gemini(sdk),
        None,
        "m",
        tmp_path,
        make_photo(),
        make_photo(),
        zones,
        render_materials,
        None,
        None,
    )
    assert img.size == (8, 8)
