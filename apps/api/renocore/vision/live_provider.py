"""Real AIProvider: Gemini (C2, C5) + TypeSafe Jev (C1, C3, C4, C6)."""

from PIL.Image import Image

from renocore.schemas.entities import (
    LabelAnswer,
    Material,
    MaterialAdvice,
    QAResult,
    Region,
    SegmentCandidate,
    WholePhotoAnswers,
    Zone,
)
from renocore.schemas.vision_io import AICallRecorder
from renocore.settings import Settings
from renocore.vision.audit import Tracer
from renocore.vision.gemini_adapter import GeminiClient
from renocore.vision.jev_adapter import JevClient
from renocore.vision.memo import FileCache
from renocore.vision.stages import compose as render
from renocore.vision.stages import full_image as whole_photo
from renocore.vision.stages import guidance as advice
from renocore.vision.stages import partition as segment
from renocore.vision.stages import tags as labels
from renocore.vision.stages import verify as check


class RealProvider:
    def __init__(
        self,
        settings: Settings,
        recorder: AICallRecorder | None = None,
        *,
        jev: JevClient | None = None,
        gemini: GeminiClient | None = None,
        cache: FileCache | None = None,
    ) -> None:
        self.settings = settings
        self.tracer = Tracer(recorder)
        self.cache = cache if cache is not None else FileCache(settings.storage_root / "ai_cache")
        self.jev = jev or JevClient(
            api_key=settings.jev_api_key,
            model=settings.jev_model,
            max_concurrency=settings.jev_max_concurrency,
            tracer=self.tracer,
            cache=self.cache,
        )
        self.gemini = gemini or GeminiClient(
            api_key=settings.gemini_api_key,
            max_concurrency=settings.gemini_max_concurrency,
            tracer=self.tracer,
        )

    async def whole_photo(self, photo: Image) -> WholePhotoAnswers:
        return await whole_photo.run(self.jev, photo)

    async def segment(self, photo: Image) -> list[SegmentCandidate]:
        return await segment.run(
            self.gemini,
            self.cache,
            self.settings.gemini_segment_model,
            photo,
            image_model=self.settings.gemini_image_model,
        )

    async def label_regions(self, photo: Image, regions: list[Region]) -> dict[str, LabelAnswer]:
        return await labels.run(self.jev, photo, regions)

    async def material_advice(
        self, photo: Image, regions: list[Region], materials: dict[str, Material]
    ) -> list[MaterialAdvice]:
        return await advice.run(self.jev, photo, regions, materials, self.settings.seed_dir)

    async def generate_redesign(
        self,
        photo: Image,
        zone_map: Image,
        zones: list[Zone],
        materials: dict[str, Material],
        user_note: str | None = None,
        fix_notes: list[str] | None = None,
        attempt: int = 0,
        cache_salt: str | None = None,
    ) -> Image:
        return await render.generate(
            self.gemini,
            self.cache,
            self.settings.gemini_image_model,
            self.settings.seed_dir,
            photo,
            zone_map,
            zones,
            materials,
            user_note,
            fix_notes,
            attempt,
            cache_salt,
        )

    async def check_render(
        self,
        original: Image,
        result: Image,
        zone_map: Image,
        zones: list[Zone],
        materials: dict[str, Material],
    ) -> QAResult:
        return await check.run(
            self.jev,
            original,
            result,
            zone_map,
            zones,
            materials,
            self.settings.seed_dir,
            self.settings.render_qa_threshold,
        )

    async def aclose(self) -> None:
        await self.jev.aclose()
