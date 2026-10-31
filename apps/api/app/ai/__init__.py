"""AI integration: Gemini + Jev clients, calls C1-C6, rules, fake provider.

Public interface - keep these names and signatures.
"""

from app.ai.fake import FakeProvider
from app.ai.real import RealProvider
from app.ai.rules import apply_labels, photo_verdict, proposed_regions
from app.ai.steps.render import RenderOutcome, render_design
from app.ai.steps.segment import SegmentationError
from app.config import Settings
from app.domain.ai import AICallRecorder, AIProvider


def get_provider(settings: Settings, recorder: AICallRecorder | None = None) -> AIProvider:
    """Real provider (Gemini + Jev) or fake (recorded fixtures) per settings.ai_provider."""
    if settings.ai_provider == "fake":
        return FakeProvider(settings, recorder)
    return RealProvider(settings, recorder)


__all__ = [
    "FakeProvider",
    "RealProvider",
    "RenderOutcome",
    "SegmentationError",
    "apply_labels",
    "get_provider",
    "photo_verdict",
    "proposed_regions",
    "render_design",
]
