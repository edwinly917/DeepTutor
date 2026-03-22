from __future__ import annotations

from pathlib import Path
from typing import Any

from src.services.ppt.image_generator import ImageGenerator
from src.services.ppt.outline_generator import OutlineGenerator


class BananaPptService(ImageGenerator):
    def __init__(self, project_root: Path):
        super().__init__(project_root)
        self.outline_generator = OutlineGenerator(project_root)
        self.outline_generator.config = self.config

    async def generate_outline(
        self,
        source_content: str,
        style_prompt: str | None = None,
        max_slides: int | None = None,
        language: str = "zh",
        source_type: str = "from_sources",
    ) -> dict[str, Any]:
        return await self.outline_generator.generate_outline(
            source_content,
            style_prompt=style_prompt,
            max_slides=max_slides,
            language=language,
            source_type=source_type,
        )

    def _build_image_generation_prompt(
        self,
        prompt: str,
        slide_title: str | None,
        slide_points: list[str] | None,
        layout: str | None,
        deck_title: str | None,
        style_prompt: str | None,
        simplified: bool = False,
    ) -> str:
        return self.build_image_prompt(
            prompt=prompt,
            slide_title=slide_title,
            slide_points=slide_points,
            layout=layout,
            deck_title=deck_title,
            style_prompt=style_prompt,
            simplified=simplified,
        )


__all__ = ["BananaPptService"]
