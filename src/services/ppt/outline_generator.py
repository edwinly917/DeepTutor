from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from src.logging import get_logger
from src.services.config import get_banana_ppt_config
from src.services.llm import complete as llm_complete
from src.services.llm import get_llm_config, get_token_limit_kwargs
from src.services.ppt.prompts import PptPromptManager

logger = get_logger("PPTOutlineGenerator")

_LAYOUTS = {
    "SECTION_HEADER",
    "OVERVIEW",
    "SPLIT_IMAGE_LEFT",
    "SPLIT_IMAGE_RIGHT",
    "TOP_IMAGE",
    "TYPOGRAPHIC_WITH_IMAGE",
    "QUOTE",
    "TYPOGRAPHIC",
    "SPLIT_LEFT",
    "SPLIT_RIGHT",
}


class OutlineGenerator:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.config = get_banana_ppt_config(project_root)

    async def generate_outline(
        self,
        source_content: str,
        *,
        style_prompt: str | None = None,
        style_context=None,
        max_slides: int | None = None,
        language: str = "zh",
        source_type: str = "from_sources",
        reference_files: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if not source_content:
            raise ValueError("source_content is empty")

        max_slides = max(1, int(max_slides or self.config.max_slides))
        trimmed_content = self._trim_source(source_content)
        resolved_style_context = style_context or PptPromptManager.resolve_style_context(
            style_custom_text=(style_prompt or "").strip()
        )
        system_prompt = PptPromptManager.outline_system(language)
        user_prompt = PptPromptManager.outline_user(
            source_type=source_type,
            source_brief=trimmed_content,
            max_slides=max_slides,
            style_context=resolved_style_context,
            language=language,
            reference_files=reference_files,
        )

        outline_cfg = self.config.outline
        llm_cfg = get_llm_config()
        model = outline_cfg.model or llm_cfg.model
        api_key = outline_cfg.api_key or llm_cfg.api_key
        base_url = outline_cfg.base_url or llm_cfg.base_url
        binding = outline_cfg.binding or llm_cfg.binding

        if not model:
            raise ValueError("No LLM model configured for outline generation")

        kwargs = {"temperature": outline_cfg.temperature}
        kwargs.update(get_token_limit_kwargs(model, outline_cfg.max_tokens))

        raw = await llm_complete(
            prompt=user_prompt,
            system_prompt=system_prompt,
            model=model,
            api_key=api_key,
            base_url=base_url,
            binding=binding,
            **kwargs,
        )

        data = self._extract_json(raw)
        if not data:
            raise ValueError("Failed to parse outline JSON")
        return self._normalize_outline(data, max_slides)

    def _trim_source(self, source: str) -> str:
        return (source or "").strip()

    def _normalize_outline(self, outline: dict[str, Any], max_slides: int) -> dict[str, Any]:
        title = str(outline.get("title") or "Presentation")
        subtitle = str(outline.get("subtitle") or "")
        theme_color = self._normalize_hex(outline.get("themeColor"), "#3b82f6")
        accent_color = self._normalize_hex(outline.get("accentColor"), "#f59e0b")

        slides = []
        for slide in outline.get("slides") or []:
            if not isinstance(slide, dict):
                continue
            slide_title = str(slide.get("title") or "Slide")
            points = [str(point) for point in (slide.get("points") or []) if str(point).strip()]
            layout = str(slide.get("layout") or "TYPOGRAPHIC")
            if layout not in _LAYOUTS:
                layout = "TYPOGRAPHIC"
            slides.append(
                {
                    "title": slide_title,
                    "points": points,
                    "layout": layout,
                }
            )
            if len(slides) >= max_slides:
                break

        if not slides:
            slides = [{"title": "Overview", "points": [], "layout": "TYPOGRAPHIC"}]

        return {
            "title": title,
            "subtitle": subtitle,
            "themeColor": theme_color,
            "accentColor": accent_color,
            "slides": slides,
        }

    def _normalize_hex(self, value: Any, fallback: str) -> str:
        if not value:
            return fallback
        text = str(value).strip()
        if not text.startswith("#"):
            text = f"#{text}"
        if re.match(r"^#[0-9a-fA-F]{6}$", text):
            return text.lower()
        return fallback

    def _extract_json(self, text: str) -> dict[str, Any] | None:
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        match = re.search(r"```json\s*([\s\S]*?)\s*```", text, flags=re.IGNORECASE)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except Exception:
                pass

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except Exception:
                return None
        return None
