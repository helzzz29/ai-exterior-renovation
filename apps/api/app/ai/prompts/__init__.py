"""Versioned prompt templates. Bump the file name (segment_v2.md) to change a prompt."""

from functools import cache
from pathlib import Path
from string import Template

PROMPTS_DIR = Path(__file__).parent

SEGMENT_PROMPT = "segment_v1"  # mask output mode
SEGMENT_POLYGON_PROMPT = "segment_v2"  # polygon output mode
SEGMENT_LABELMAP_PROMPT = "segment_v3"  # label-map output mode (default, image model)
RENDER_PROMPT = "render_v1"


@cache
def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def render_prompt(name: str, **values: str) -> str:
    """Fill `$placeholders` in a prompt template (missing values raise KeyError)."""
    return Template(load_prompt(name)).substitute(**values)
