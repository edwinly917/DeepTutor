from __future__ import annotations

import json
from textwrap import dedent

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

_SOURCE_RULES = {
    "from_research": [
        "Preserve the report's real argument order, conclusion hierarchy, and decision relevance.",
        "Synthesize findings instead of copying raw section headings unless they are already presentation-ready.",
        "Promote key conclusions, risks, and implications to prominent slides.",
    ],
    "from_notebook": [
        "Find structure across scattered notes instead of listing records one by one.",
        "Group related ideas into a coherent narrative: context, core ideas, analysis, and takeaways.",
        "If notes contain tension or multiple viewpoints, reflect the contrast clearly instead of flattening it.",
    ],
    "from_sources": [
        "Synthesize across sources instead of summarizing each source in order.",
        "Highlight consensus, divergence, and complementary evidence when it helps the story.",
        "Organize by themes and insights, not by source list order.",
    ],
}


class PptPromptManager:
    @staticmethod
    def _language_instruction(language: str | None) -> str:
        return _LANGUAGE_INSTRUCTIONS.get((language or "zh").lower(), _LANGUAGE_INSTRUCTIONS["zh"])

    @staticmethod
    def _normalize_source_type(source_type: str | None) -> str:
        source = (source_type or "from_sources").strip().lower()
        if source in _SOURCE_RULES:
            return source
        if source in {"research", "report"}:
            return "from_research"
        if source in {"notebook", "notes"}:
            return "from_notebook"
        return "from_sources"

    @staticmethod
    def _bullet_join(items: list[str]) -> str:
        cleaned = [str(item).strip() for item in items if str(item).strip()]
        return "\n".join(f"- {item}" for item in cleaned) or "- None"

    @classmethod
    def outline_system(cls, language: str = "zh") -> str:
        return dedent(
            f"""
            You are an elite presentation information architect.

            Turn source material into a professional slide-deck outline with clear logic,
            strong narrative flow, and visual planning intent.

            Return ONLY valid JSON with this schema:
            {{
              "title": string,
              "subtitle": string,
              "themeColor": string,
              "accentColor": string,
              "slides": [
                {{
                  "title": string,
                  "points": [string],
                  "layout": string,
                  "imagePrompt": string
                }}
              ]
            }}

            Global rules:
            - Output JSON only, with no markdown or commentary.
            - themeColor and accentColor must be valid hex colors such as "#3b82f6".
            - subtitle should be concise; use "" when unnecessary.
            - Each slide must communicate one main message.
            - Each slide title should read like a presentation headline, not a raw source heading.
            - Each slide must contain 3-5 concise, non-redundant points.
            - Use the requested language consistently.
            - Vary layouts naturally and do not repeat the same layout more than twice in a row.
            - The first slide should establish topic, context, and stakes.
            - The last slide should close with implications, decisions, or takeaways.

            {cls._language_instruction(language)}
            """
        ).strip()

    @classmethod
    def outline_user(
        cls,
        *,
        source_type: str,
        content: str,
        max_slides: int,
        style_prompt: str | None,
        language: str = "zh",
    ) -> str:
        source = cls._normalize_source_type(source_type)
        source_rules = "\n".join(f"- {rule}" for rule in _SOURCE_RULES[source])
        source_label = {
            "from_research": "deep research report",
            "from_notebook": "selected notebook notes",
            "from_sources": "multi-source synthesized material",
        }[source]
        return dedent(
            f"""
            Build a PPT outline from the {source_label} below.

            Deck contract:
            - Language: {language}
            - Max slides: {max_slides}
            - Stay faithful to the source substance and priority order.
            - Compress lower-priority details when needed to fit the slide limit.
            - Prefer synthesis over copying long source phrases.

            Source-specific goals:
            {source_rules}

            Visual planning brief:
            {style_prompt or "default"}
            - Style affects only tone, density, pacing, palette tendency, and layout rhythm.
            - Do not let style override the factual hierarchy of the source.

            Use only these layout values:
            {json.dumps(_LAYOUT_VALUES, ensure_ascii=False)}

            Layout guidance:
            - Choose layout based on slide function, not decoration.
            - Use image-oriented layouts only when the slide benefits from a strong supporting visual.

            imagePrompt guidance:
            - imagePrompt must directly support the slide's message.
            - Describe one professional 16:9 presentation visual concept.
            - Include subject, setting, composition, and mood when helpful.
            - Prefer editorial, business, analytical, or conceptual visuals.
            - Avoid logos, watermarks, readable text, UI screenshots, fantasy spectacle, or decorative-only imagery.

            Source material:
            {content}
            """
        ).strip()

    @classmethod
    def style_briefs(
        cls,
        *,
        preset_text: str,
        reference_style_prompt: str,
        user_override: str,
    ) -> tuple[str, str]:
        system_prompt = dedent(
            """
            You are a presentation style planner.

            Return ONLY valid JSON with keys:
            - outline_style_brief
            - description_style_brief
            - image_style_brief

            Rules:
            - outline_style_brief should cover tone, density, pacing, palette tendency, and layout rhythm only.
            - description_style_brief can additionally include typography mood, negative space, and image treatment.
            - image_style_brief can be the richest and most visually specific.
            - Keep all briefs concise, production-ready, and non-redundant.
            - User override has the highest priority.
            - Do not invent a brand identity that is not implied by the inputs.
            """
        ).strip()
        user_prompt = dedent(
            f"""
            Preset base:
            {preset_text or "None"}

            Reference-image summary:
            {reference_style_prompt or "None"}

            User override:
            {user_override or "None"}

            Return concise briefs for PPT outline planning, slide description writing, and image generation.
            """
        ).strip()
        return system_prompt, user_prompt

    @classmethod
    def page_description(
        cls,
        *,
        page_index: int,
        slide_title: str,
        slide_points: list[str],
        deck_outline_summary: str,
        supporting_context: str,
        style_brief: str | None,
        detail_level: str,
        language: str,
    ) -> tuple[str, str]:
        system_prompt = dedent(
            """
            You expand a confirmed PPT outline into a production-ready single-slide brief.

            Return ONLY valid JSON with keys:
            - text
            - image_prompt

            Rules:
            - Follow the current slide only; do not redesign the deck.
            - Use supporting evidence to enrich the slide, not replace its structure.
            - Keep the copy concise, specific, and presentation-ready.
            - image_prompt must align with the slide's message and visual brief.
            """
        ).strip()
        first_slide_rule = (
            "First-slide rule: keep the slide minimal, focusing on title, subtitle, speaker, and opening mood."
            if page_index == 1
            else "Do not overload the slide with unnecessary exposition."
        )
        user_prompt = dedent(
            f"""
            Deck outline summary:
            {deck_outline_summary or "No deck outline summary available."}

            Current slide (page {page_index}):
            - Title: {slide_title}
            - Points:
            {cls._bullet_join(slide_points)}

            Supporting context:
            {supporting_context or "No supporting evidence available."}

            Visual brief:
            {style_brief or "default"}

            Detail level:
            {_DETAIL_LEVEL_SPECS.get(detail_level, _DETAIL_LEVEL_SPECS["default"])}

            Additional rules:
            - Keep the slide faithful to its current meaning.
            - Avoid repeating bullet points verbatim.
            - Make the text vivid enough to drive visual production, but still concise.
            - image_prompt should describe one 16:9 professional presentation visual concept.
            - Avoid logos, readable text, screenshots, fantasy imagery, and decorative-only visuals.
            - {cls._language_instruction(language)}
            - {first_slide_rule}

            Return JSON only.
            """
        ).strip()
        return system_prompt, user_prompt

    @classmethod
    def image_generation(
        cls,
        *,
        image_prompt: str,
        slide_title: str | None,
        slide_points: list[str] | None,
        layout: str | None,
        deck_title: str | None,
        style_prompt: str | None,
        simplified: bool = False,
    ) -> str:
        points = [str(point).strip() for point in (slide_points or []) if str(point).strip()]
        lines = [
            "You are an expert presentation visual designer.",
            "Create one professional slide illustration that supports the slide message directly.",
        ]
        if deck_title:
            lines.append(f"Deck title: {deck_title}")
        if slide_title:
            lines.append(f"Slide title: {slide_title}")
        if points and not simplified:
            lines.append("Slide key points:")
            lines.extend(f"- {point}" for point in points[:5])
        if layout and not simplified:
            lines.append(f"Target layout: {layout}")
        if style_prompt and not simplified:
            lines.append(f"Visual style guidance: {style_prompt}")
        lines.extend(
            [
                "Design guidelines:",
                "- 16:9 composition, presentation-ready, clean hierarchy, strong focal point.",
                "- Leave usable negative space for slide copy and layout overlays.",
                "- Prefer editorial, business, analytical, or conceptual visuals over generic decoration.",
                "- If the slide is abstract or data-heavy, use a business/editorial metaphor instead of a literal screenshot or chart capture.",
                "Hard constraints:",
                "- Avoid logos, watermarks, readable text, UI screenshots, dense tables, and fantasy spectacle.",
                "- Avoid clutter and overly literal stock-photo cliches.",
                f"Image brief: {image_prompt}",
            ]
        )
        return "\n".join(lines)

    @classmethod
    def chat_edit_classifier(
        cls,
        *,
        slide_title: str,
        slide_points: list[str],
        user_message: str,
    ) -> tuple[str, str]:
        system_prompt = dedent(
            """
            You classify a slide editing request.

            Return ONLY valid JSON with key edit_type.
            Allowed values: outline_edit, description_edit, image_edit.
            """
        ).strip()
        user_prompt = dedent(
            f"""
            Slide title: {slide_title}
            Slide points:
            {cls._bullet_join(slide_points)}

            User request:
            {user_message}

            Classify which part of the slide the user mainly wants to change.
            """
        ).strip()
        return system_prompt, user_prompt

    @classmethod
    def rewrite_outline(
        cls,
        *,
        current_title: str,
        current_points: list[str],
        user_message: str,
    ) -> tuple[str, str]:
        system_prompt = (
            "You rewrite slide outline content based on user instruction. "
            "Return ONLY valid JSON with keys title, points, assistant_message."
        )
        user_prompt = dedent(
            f"""
            Current title: {current_title}
            Current points:
            {cls._bullet_join(current_points)}

            Instruction:
            {user_message}

            Rewrite the slide title and bullet points.
            - Keep the title concise and presentation-ready.
            - Return 3-5 bullet points.
            - assistant_message should briefly confirm what changed.
            """
        ).strip()
        return system_prompt, user_prompt

    @classmethod
    def rewrite_description(
        cls,
        *,
        slide_title: str,
        slide_points: list[str],
        current_description: str,
        user_message: str,
    ) -> tuple[str, str]:
        system_prompt = (
            "You rewrite slide description content based on user instruction. "
            "Return ONLY valid JSON with keys description_text, assistant_message."
        )
        user_prompt = dedent(
            f"""
            Slide title: {slide_title}
            Slide points:
            {cls._bullet_join(slide_points)}

            Current description:
            {current_description or "None"}

            Instruction:
            {user_message}

            Write an updated single-slide description that can drive image generation and slide production.
            """
        ).strip()
        return system_prompt, user_prompt

    @classmethod
    def rewrite_image_prompt(
        cls,
        *,
        slide_title: str,
        slide_points: list[str],
        current_prompt: str,
        user_message: str,
    ) -> tuple[str, str]:
        system_prompt = (
            "You rewrite a slide image prompt based on user instruction. "
            "Return ONLY valid JSON with keys image_prompt, assistant_message."
        )
        user_prompt = dedent(
            f"""
            Slide title: {slide_title}
            Slide points:
            {cls._bullet_join(slide_points)}

            Current image prompt:
            {current_prompt or "None"}

            Instruction:
            {user_message}

            Write one improved image prompt for a professional 16:9 presentation visual.
            """
        ).strip()
        return system_prompt, user_prompt

    @staticmethod
    def reference_style_extraction() -> tuple[str, str]:
        system_prompt = (
            "You are a professional PPT design analyst. "
            "Return ONLY valid JSON with keys style_prompt, palette_hint, composition_hint."
        )
        user_prompt = dedent(
            """
            Analyze the reference image and extract PPT visual guidance.
            Focus on:
            - color palette and contrast pattern
            - typography mood
            - layout rhythm and negative space
            - image treatment, texture, and lighting

            style_prompt should be concise but specific enough to guide slide generation.
            palette_hint should summarize the dominant colors.
            composition_hint should summarize layout tendencies and focal structure.
            """
        ).strip()
        return system_prompt, user_prompt
