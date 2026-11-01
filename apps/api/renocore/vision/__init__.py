"""AI integration: Gemini + Jev clients, calls C1-C6, rules, fake provider.

Public interface - keep these names and signatures.
"""

from renocore.schemas.vision_io import AICallRecorder, AIProvider
from renocore.settings import Settings
from renocore.vision.guardrails import apply_labels, photo_verdict, proposed_regions
from renocore.vision.live_provider import RealProvider
from renocore.vision.stages.compose import RenderOutcome, render_design
from renocore.vision.stages.partition import SegmentationError
from renocore.vision.stub import FakeProvider


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
