from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
from string import Template
from typing import Any
from xml.sax.saxutils import escape

from src.services.ppt.preset_styles import (
    DEFAULT_PRESET_STYLE_ID,
    PptPresetStyle,
    get_preset_style,
    list_preset_styles,
)

_ASSET_ROOT = Path(__file__).resolve().parent / "prompt_assets"

_LAYOUT_VALUES = [
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
]

_DETAIL_LEVEL_SPECS = {
    "concise": "Keep copy extremely compressed and presentation-like.",
    "default": "Keep each idea crisp and easy to render on a slide. Prefer short phrases over long prose.",
    "detailed": "Add more supporting detail while keeping a slide-ready structure and clear hierarchy.",
}

_LANGUAGE_INSTRUCTIONS = {
    "zh": "Use Chinese for all deck text and slide copy.",
    "en": "Use English for all deck text and slide copy.",
    "ja": "Use Japanese for all deck text and slide copy.",
}


@dataclass(frozen=True)
class StyleContext:
    preset_id: str
    preset_name_zh: str
    preset_name_en: str
    preset_color: str
    preset_description_zh: str
    preset_description_en: str
    custom_text: str = ""
    reference_style_prompt: str = ""
    reference_layout_prompt: str = ""
    reference_content_prompt: str = ""

    def preset_description(self, language: str = "zh") -> str:
        if (language or "zh").lower().startswith("zh"):
            return self.preset_description_zh or self.preset_description_en
        return self.preset_description_en or self.preset_description_zh

    def style_summary(self, language: str = "zh") -> str:
        blocks = [f"Preset ({self.preset_id}):\n{self.preset_description(language)}"]
        if self.custom_text:
            blocks.append(f"User customization:\n{self.custom_text}")
        if self.reference_style_prompt:
            blocks.append(f"Template style cues:\n{self.reference_style_prompt}")
        if self.reference_layout_prompt:
            blocks.append(f"Template layout cues:\n{self.reference_layout_prompt}")
        if self.reference_content_prompt:
            blocks.append(f"Template content cues:\n{self.reference_content_prompt}")
        return "\n\n".join(block for block in blocks if block.strip()).strip()

    def preview_prompt(self, language: str = "zh") -> str:
        lines = [
            f"Preset: {self.preset_name_zh if language == 'zh' else self.preset_name_en}",
            f"Color: {self.preset_color}",
            self.preset_description(language),
        ]
        if self.custom_text:
            lines.extend(["User customization:", self.custom_text])
        if self.reference_style_prompt:
            lines.extend(["Template style cues:", self.reference_style_prompt])
        if self.reference_layout_prompt:
            lines.extend(["Template layout cues:", self.reference_layout_prompt])
        if self.reference_content_prompt:
            lines.extend(["Template content cues:", self.reference_content_prompt])
        return "\n".join(line for line in lines if line.strip()).strip()


class PptPromptManager:
    @staticmethod
    def _language_instruction(language: str | None) -> str:
        return _LANGUAGE_INSTRUCTIONS.get((language or "zh").lower(), _LANGUAGE_INSTRUCTIONS["zh"])

    @staticmethod
    def _normalize_source_type(source_type: str | None) -> str:
        source = (source_type or "from_sources").strip().lower()
        if source in {"from_research", "research", "report"}:
            return "from_research"
        if source in {"from_notebook", "notebook", "notes"}:
            return "from_notebook"
        return "from_sources"

    @staticmethod
    def _bullet_join(items: list[str]) -> str:
        cleaned = [str(item).strip() for item in items if str(item).strip()]
        return "\n".join(f"- {item}" for item in cleaned) or "- None"

    @staticmethod
    def _compact_text(value: str | None, fallback: str) -> str:
        text = (value or "").strip()
        return text or fallback

    @classmethod
    @lru_cache(maxsize=None)
    def _load_template(cls, relative_path: str) -> Template:
        asset_path = _ASSET_ROOT / relative_path
        return Template(asset_path.read_text(encoding="utf-8"))

    @classmethod
    def _render_template(cls, relative_path: str, **variables: Any) -> str:
        normalized = {
            key: ("" if value is None else str(value)) for key, value in variables.items()
        }
        return cls._load_template(relative_path).safe_substitute(normalized).strip()

    @staticmethod
    def _xml_block(tag: str, content: str | None) -> str:
        text = (content or "").strip()
        if not text:
            return ""
        return f"<{tag}>\n{escape(text)}\n</{tag}>"

    @classmethod
    def _format_reference_files_xml(cls, reference_files: list[dict[str, Any]] | None) -> str:
        items = reference_files or []
        if not items:
            return ""
        blocks: list[str] = []
        for index, item in enumerate(items, start=1):
            title = escape(str(item.get("title") or f"Reference {index}").strip())
            kind = escape(str(item.get("type") or "reference").strip())
            source_key = escape(str(item.get("source_key") or item.get("id") or "").strip())
            summary = escape(
                str(item.get("summary") or item.get("excerpt") or item.get("content") or "").strip()
            )
            lines = [f'<file index="{index}" type="{kind}">', f"<title>{title}</title>"]
            if source_key:
                lines.append(f"<source_key>{source_key}</source_key>")
            if summary:
                lines.append(f"<summary>{summary}</summary>")
            lines.append("</file>")
            blocks.append("\n".join(lines))
        return "<reference_files>\n" + "\n".join(blocks) + "\n</reference_files>"

    @classmethod
    def _format_reference_context_xml(
        cls,
        *,
        style_context: StyleContext | None = None,
        template_analysis: dict[str, str] | None = None,
        reference_files: list[dict[str, Any]] | None = None,
        source_brief: str | None = None,
        source_anchors: str | None = None,
    ) -> str:
        blocks: list[str] = []
        if style_context:
            blocks.append(
                cls._xml_block(
                    "style_context",
                    style_context.preview_prompt(),
                )
            )
        if template_analysis:
            blocks.append(
                cls._xml_block(
                    "template_analysis",
                    "\n".join(
                        [
                            f"Style: {(template_analysis.get('reference_style_prompt') or '').strip()}",
                            f"Layout: {(template_analysis.get('reference_layout_prompt') or '').strip()}",
                            f"Content: {(template_analysis.get('reference_content_prompt') or '').strip()}",
                        ]
                    ).strip(),
                )
            )
        blocks.append(cls._format_reference_files_xml(reference_files))
        blocks.append(cls._xml_block("source_brief", source_brief))
        blocks.append(cls._xml_block("source_anchors", source_anchors))
        return (
            "\n\n".join(block for block in blocks if block.strip()).strip()
            or "<reference_context />"
        )

    @staticmethod
    def list_style_presets() -> list[dict[str, Any]]:
        return list_preset_styles()

    @staticmethod
    def resolve_style_context(
        *,
        style_preset_id: str | None = None,
        style_custom_text: str | None = None,
        reference_style_prompt: str | None = None,
        reference_layout_prompt: str | None = None,
        reference_content_prompt: str | None = None,
    ) -> StyleContext:
        preset = get_preset_style(style_preset_id or DEFAULT_PRESET_STYLE_ID)
        return StyleContext(
            preset_id=preset.id,
            preset_name_zh=preset.name_zh,
            preset_name_en=preset.name_en,
            preset_color=preset.color,
            preset_description_zh=preset.description_zh.strip(),
            preset_description_en=preset.description_en.strip(),
            custom_text=(style_custom_text or "").strip(),
            reference_style_prompt=(reference_style_prompt or "").strip(),
            reference_layout_prompt=(reference_layout_prompt or "").strip(),
            reference_content_prompt=(reference_content_prompt or "").strip(),
        )

    @staticmethod
    def default_style_context() -> StyleContext:
        return PptPromptManager.resolve_style_context()

    @staticmethod
    def style_briefs(style_context: StyleContext, language: str = "zh") -> tuple[str, str]:
        system_prompt = (
            "You are a presentation style planner. "
            "Return ONLY valid JSON with keys outline_style_brief, description_style_brief, image_style_brief. "
            "outline_style_brief should cover tone, density, pacing, palette tendency, and layout rhythm only. "
            "description_style_brief may additionally cover typography mood, negative space, and image treatment. "
            "image_style_brief can be the richest and most visually specific. "
            "User customization has the highest priority, then template cues, then preset baseline."
        )
        user_prompt = "\n\n".join(
            [
                "Build concise, production-ready style briefs for the PPT pipeline.",
                f"Language target: {language}",
                f"Preset baseline:\n{style_context.preset_description(language)}",
                f"User customization:\n{style_context.custom_text or 'None'}",
                f"Template style cues:\n{style_context.reference_style_prompt or 'None'}",
                f"Template layout cues:\n{style_context.reference_layout_prompt or 'None'}",
                f"Template content cues:\n{style_context.reference_content_prompt or 'None'}",
            ]
        ).strip()
        return system_prompt, user_prompt

    @classmethod
    def normalization_prompt(
        cls,
        *,
        source_type: str,
        source_content: str,
        reference_context_xml: str = "",
        language: str = "zh",
    ) -> tuple[str, str]:
        normalized_source_type = cls._normalize_source_type(source_type)
        template_name = {
            "from_research": "normalization/research_to_deck_source.md",
            "from_notebook": "normalization/notebook_to_deck_source.md",
            "from_sources": "normalization/sources_to_deck_source.md",
        }[normalized_source_type]
        system_prompt = (
            "You are a presentation strategist. Transform raw DeepTutor source material into a "
            "DeckSourceBrief for downstream PPT planning. Return Markdown only."
        )
        user_prompt = cls._render_template(
            template_name,
            source_content=source_content,
            reference_context_xml=reference_context_xml,
            language_instruction=cls._language_instruction(language),
        )
        return system_prompt, user_prompt

    @classmethod
    def outline_system(cls, language: str = "zh") -> str:
        return cls._render_template(
            "outline/system.md",
            language_instruction=cls._language_instruction(language),
        )

    @classmethod
    def outline_user(
        cls,
        *,
        source_type: str,
        source_brief: str,
        max_slides: int,
        style_context: StyleContext,
        language: str = "zh",
        reference_files: list[dict[str, Any]] | None = None,
    ) -> str:
        normalized_source_type = cls._normalize_source_type(source_type)
        template_name = {
            "from_research": "outline/from_research.md",
            "from_notebook": "outline/from_notebook.md",
            "from_sources": "outline/from_sources.md",
        }[normalized_source_type]
        reference_context_xml = cls._format_reference_context_xml(
            style_context=style_context,
            template_analysis={
                "reference_style_prompt": style_context.reference_style_prompt,
                "reference_layout_prompt": style_context.reference_layout_prompt,
                "reference_content_prompt": style_context.reference_content_prompt,
            },
            reference_files=reference_files,
        )
        return cls._render_template(
            template_name,
            language=language,
            max_slides=max_slides,
            style_summary=cls._compact_text(style_context.style_summary(language), "Default"),
            reference_context_xml=reference_context_xml,
            layout_values_json=json.dumps(_LAYOUT_VALUES, ensure_ascii=False),
            source_brief=source_brief,
        )

    @classmethod
    def page_description(
        cls,
        *,
        page_index: int,
        slide_title: str,
        slide_points: list[str],
        deck_outline_summary: str,
        supporting_context: str,
        style_context: StyleContext,
        detail_level: str,
        language: str,
    ) -> tuple[str, str]:
        system_prompt = (
            "你负责把确认好的PPT大纲展开为可直接渲染的单页描述。"
            "Return ONLY valid JSON with keys page_title, subtitle, page_text, material_images."
        )
        first_slide_rule = (
            "第一页规则：保持极简，只放标题、副标题以及演讲人等，不添加任何多余内容。"
            if page_index == 1
            else "不要在页面上堆砌不必要的内容。"
        )
        user_prompt = cls._render_template(
            "description/page.md",
            deck_outline_summary=deck_outline_summary or "No deck outline summary available.",
            page_index=page_index,
            slide_title=slide_title,
            bullet_points=cls._bullet_join(slide_points),
            supporting_context=supporting_context or "No supporting evidence available.",
            style_summary=cls._compact_text(style_context.preset_description(language), "Default"),
            detail_level_spec=_DETAIL_LEVEL_SPECS.get(detail_level, _DETAIL_LEVEL_SPECS["default"]),
            language_instruction=cls._language_instruction(language),
            first_slide_rule=first_slide_rule,
        )
        return system_prompt, user_prompt

    @classmethod
    def _build_page_description_block(cls, description_content: dict[str, Any]) -> str:
        """Build banana-slides style page_description from description_content."""
        lines: list[str] = []
        page_title = cls._clean_for_render(description_content.get("page_title") or "")
        if page_title:
            lines.append(f"页面标题：{page_title}")
        subtitle = cls._clean_for_render(description_content.get("subtitle") or "")
        if subtitle:
            lines.append(f"副标题：{subtitle}")
        lines.append("")
        text = cls._clean_for_render(description_content.get("text") or "")
        if text:
            lines.append("页面文字：")
            lines.append(text)
        material_images = description_content.get("material_images") or []
        if material_images:
            lines.append("")
            lines.append("图片素材：")
            for img in material_images:
                lines.append(str(img).strip())
        return "\n".join(lines).strip()

    @staticmethod
    def _clean_for_render(text: str) -> str:
        """Strip markdown formatting that would pollute rendered slide images."""
        import re

        cleaned = (text or "").strip()
        if not cleaned:
            return ""
        cleaned = re.sub(r"^#{1,6}\s*", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"\*{1,3}(.+?)\*{1,3}", r"\1", cleaned)
        cleaned = re.sub(r"^[\-\*_]{3,}\s*$", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"```[^\n]*\n?", "", cleaned)
        cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
        cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    @classmethod
    def image_generation(
        cls,
        *,
        description_content: dict[str, Any],
        slide_title: str | None = None,
        style_context: StyleContext,
        page_index: int = 1,
        language: str = "zh",
        simplified: bool = False,
    ) -> str:
        page_description = cls._build_page_description_block(description_content)
        if not page_description:
            page_description = f"页面标题：{slide_title or 'Untitled'}"

        if simplified:
            style_guidance = "采用简洁专业的设计风格。"
            language_instruction = ""
            cover_page_instruction = ""
        else:
            preset_desc = (style_context.preset_description(language) or "").strip()
            style_guidance = preset_desc if preset_desc else "采用简洁专业的设计风格。"
            language_instruction = _LANGUAGE_INSTRUCTIONS.get(
                (language or "zh").lower(), _LANGUAGE_INSTRUCTIONS["zh"]
            )
            cover_page_instruction = (
                "**注意：当前页面为ppt的封面页，请你采用专业的封面设计美学技巧，"
                "务必凸显出页面标题，分清主次，确保一下就能抓住观众的注意力。**"
                if page_index == 1
                else ""
            )

        return cls._render_template(
            "image/generation.md",
            page_description=page_description,
            style_guidance=style_guidance,
            language_instruction=language_instruction,
            cover_page_instruction=cover_page_instruction,
        )

    @classmethod
    def chat_edit_classifier(
        cls,
        *,
        slide_title: str,
        slide_points: list[str],
        user_message: str,
        style_context: StyleContext | None = None,
    ) -> tuple[str, str]:
        system_prompt = (
            "You classify a slide editing request. Return ONLY valid JSON with key edit_type. "
            "Allowed values: outline_edit, description_edit, image_edit."
        )
        user_prompt = cls._render_template(
            "edit/classify.md",
            slide_title=slide_title,
            bullet_points=cls._bullet_join(slide_points),
            style_summary=(style_context.style_summary() if style_context else "Default"),
            user_message=user_message,
        )
        return system_prompt, user_prompt

    @classmethod
    def rewrite_outline(
        cls,
        *,
        current_title: str,
        current_points: list[str],
        user_message: str,
        style_context: StyleContext | None = None,
    ) -> tuple[str, str]:
        system_prompt = (
            "You rewrite slide outline content based on user instruction. "
            "Return ONLY valid JSON with keys title, points, assistant_message."
        )
        user_prompt = cls._render_template(
            "edit/outline.md",
            current_title=current_title,
            bullet_points=cls._bullet_join(current_points),
            user_message=user_message,
            reference_context_xml=cls._format_reference_context_xml(style_context=style_context),
        )
        return system_prompt, user_prompt

    @classmethod
    def rewrite_description(
        cls,
        *,
        slide_title: str,
        slide_points: list[str],
        current_description: str,
        user_message: str,
        style_context: StyleContext | None = None,
    ) -> tuple[str, str]:
        system_prompt = (
            "You rewrite slide description content based on user instruction. "
            "Return ONLY valid JSON with keys description_text, assistant_message."
        )
        user_prompt = cls._render_template(
            "edit/description.md",
            slide_title=slide_title,
            bullet_points=cls._bullet_join(slide_points),
            current_description=current_description or "None",
            user_message=user_message,
            reference_context_xml=cls._format_reference_context_xml(style_context=style_context),
        )
        return system_prompt, user_prompt

    @classmethod
    def rewrite_image_prompt(
        cls,
        *,
        slide_title: str,
        slide_points: list[str],
        current_prompt: str,
        user_message: str,
        style_context: StyleContext | None = None,
    ) -> tuple[str, str]:
        system_prompt = (
            "You rewrite a slide image prompt based on user instruction. "
            "Return ONLY valid JSON with keys image_prompt, assistant_message."
        )
        user_prompt = cls._render_template(
            "edit/image.md",
            slide_title=slide_title,
            bullet_points=cls._bullet_join(slide_points),
            current_prompt=current_prompt or "None",
            user_message=user_message,
            reference_context_xml=cls._format_reference_context_xml(style_context=style_context),
        )
        return system_prompt, user_prompt

    @classmethod
    def reference_style_extraction(cls) -> tuple[str, str]:
        system_prompt = (
            "You are a professional PPT design analyst. "
            "Infer the reusable deck-wide visual language behind the template image. "
            "Ignore literal page content and return ONLY valid JSON with keys "
            "style_prompt, palette_hint, composition_hint."
        )
        user_prompt = cls._render_template("analysis/style_extraction.md")
        return system_prompt, user_prompt

    @classmethod
    def layout_extraction(cls) -> tuple[str, str]:
        system_prompt = (
            "You analyze a slide template's spatial behavior. "
            "Extract reusable layout grammar only, not subject matter or style commentary. "
            "Return ONLY valid JSON with keys layout_prompt and layout_regions."
        )
        user_prompt = cls._render_template("analysis/layout_caption.md")
        return system_prompt, user_prompt

    @classmethod
    def file_content_extraction(
        cls,
        *,
        file_name: str | None = None,
        file_text: str | None = None,
    ) -> tuple[str, str]:
        system_prompt = (
            "You analyze a template file and extract reusable presentation content signals. "
            "Infer stable deck structure and page archetypes rather than echoing raw text. "
            "Return ONLY valid JSON with keys content_prompt and key_sections."
        )
        user_prompt = cls._render_template(
            "analysis/file_content_extraction.md",
            file_name=file_name or "template-file",
            file_text=file_text or "No extracted text available.",
        )
        return system_prompt, user_prompt

    @classmethod
    def visual_synthesis(cls, *, page_findings_json: str) -> tuple[str, str]:
        system_prompt = (
            "You consolidate multiple slide-template analyses into one stable deck-level reference. "
            "Keep only reusable invariants that should influence downstream PPT generation. "
            "Return ONLY valid JSON with keys reference_style_prompt and reference_layout_prompt."
        )
        user_prompt = cls._render_template(
            "analysis/visual_synthesis.md",
            page_findings_json=page_findings_json,
        )
        return system_prompt, user_prompt

    @staticmethod
    def _extract_source_anchor_block(source_brief: str) -> str:
        if not source_brief:
            return ""
        lines = source_brief.splitlines()
        blocks: list[str] = []
        capture = False
        for line in lines:
            stripped = line.strip()
            if stripped.lower() == "## source anchors":
                capture = True
                blocks.append(stripped)
                continue
            if capture and stripped.startswith("## "):
                break
            if capture:
                blocks.append(line)
        return "\n".join(blocks).strip()


__all__ = ["PptPromptManager", "StyleContext", "DEFAULT_PRESET_STYLE_ID", "PptPresetStyle"]
