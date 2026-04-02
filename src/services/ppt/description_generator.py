from __future__ import annotations

from difflib import SequenceMatcher
import re
from typing import Any, Callable

from src.services.ppt.prompts import PptPromptManager


class DescriptionGenerator:
    def __init__(self, json_complete: Callable[[str, str], dict[str, Any]]):
        self.json_complete = json_complete

    def generate_page_description(
        self,
        project: dict[str, Any],
        page: dict[str, Any],
        *,
        detail_level: str,
        deck_outline_summary: str,
        style_context,
    ) -> dict[str, Any]:
        outline = page.get("outline_content") or {}
        title = outline.get("title") or "Untitled Slide"
        points = outline.get("points") or []
        language = project.get("language") or "zh"
        supporting_context = self.build_slide_supporting_context(project, page)
        system_prompt, user_prompt = PptPromptManager.page_description(
            page_index=int(page.get("order_index", 0)) + 1,
            slide_title=title,
            slide_points=points,
            deck_outline_summary=deck_outline_summary,
            supporting_context=supporting_context,
            style_context=style_context,
            detail_level=detail_level,
            language=language,
        )
        data = self.json_complete(user_prompt, system_prompt)
        page_title = self._clean_slide_text(data.get("page_title") or "") or title
        subtitle = self._clean_slide_text(data.get("subtitle") or "")
        page_text = self._clean_slide_text(data.get("page_text") or data.get("text") or "")
        material_images = data.get("material_images") or []
        if not page_text:
            raise ValueError(f"Failed to generate description for slide '{title}'")
        return {
            "description_content": {
                "page_title": page_title,
                "subtitle": subtitle,
                "text": page_text,
                "material_images": material_images,
                "detail_level": detail_level,
            },
            "image_prompt": "",
        }

    @staticmethod
    def _clean_slide_text(text: str) -> str:
        """Strip markdown formatting symbols that pollute image generation."""
        cleaned = (text or "").strip()
        # Remove heading markers: ### Title -> Title
        cleaned = re.sub(r"^#{1,6}\s*", "", cleaned, flags=re.MULTILINE)
        # Remove bold/italic markers: **text** -> text, *text* -> text
        cleaned = re.sub(r"\*{1,3}(.+?)\*{1,3}", r"\1", cleaned)
        # Remove horizontal rules: --- or *** or ___
        cleaned = re.sub(r"^[\-\*_]{3,}\s*$", "", cleaned, flags=re.MULTILINE)
        # Remove code fences: ```...```
        cleaned = re.sub(r"```[^\n]*\n?", "", cleaned)
        # Remove inline code backticks: `code` -> code
        cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
        # Remove markdown links: [text](url) -> text
        cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
        # Collapse multiple blank lines
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    def build_deck_outline_summary(self, pages: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for index, page in enumerate(sorted(pages, key=lambda item: item["order_index"])):
            outline = page.get("outline_content") or {}
            title = (outline.get("title") or f"Slide {index + 1}").strip()
            points = outline.get("points") or []
            bullets = "; ".join(str(point).strip() for point in points if str(point).strip())
            lines.append(f"{index + 1}. {title}" + (f" — {bullets}" if bullets else ""))
        return "\n".join(lines).strip()

    def build_slide_supporting_context(
        self,
        project: dict[str, Any],
        page: dict[str, Any],
        *,
        max_chars: int = 1200,
        max_chunks: int = 4,
    ) -> str:
        source_text = (
            project.get("source_content") or project.get("normalized_content") or ""
        ).strip()
        if not source_text:
            return ""

        chunks = self._chunk_supporting_text(source_text)
        if not chunks:
            return self._trim_text(source_text, max_chars)

        outline = page.get("outline_content") or {}
        query_text = " ".join(
            [
                str(outline.get("title") or "").strip(),
                *[
                    str(point).strip()
                    for point in (outline.get("points") or [])
                    if str(point).strip()
                ],
            ]
        ).strip()
        query_tokens = self._extract_context_tokens(query_text)
        ranked = sorted(
            chunks,
            key=lambda chunk: self._score_supporting_chunk(query_text, query_tokens, chunk),
            reverse=True,
        )

        selected: list[str] = []
        total_chars = 0
        for chunk in ranked[: max(1, max_chunks * 2)]:
            normalized_chunk = chunk.strip()
            if not normalized_chunk or normalized_chunk in selected:
                continue
            next_size = total_chars + len(normalized_chunk) + (2 if selected else 0)
            if selected and next_size > max_chars:
                continue
            selected.append(normalized_chunk)
            total_chars = next_size
            if len(selected) >= max_chunks or total_chars >= max_chars:
                break

        if not selected:
            return self._trim_text(ranked[0], max_chars)
        return self._trim_text("\n\n".join(selected), max_chars)

    def _chunk_supporting_text(self, text: str, max_chunk_chars: int = 520) -> list[str]:
        raw_blocks = [block.strip() for block in re.split(r"\n\s*\n+", text) if block.strip()]
        chunks: list[str] = []
        for block in raw_blocks:
            if len(block) <= max_chunk_chars:
                chunks.append(block)
                continue

            sentences = [
                part.strip() for part in re.split(r"(?<=[。！？.!?])\s+|\n", block) if part.strip()
            ]
            current = ""
            for sentence in sentences:
                candidate = f"{current}\n{sentence}".strip() if current else sentence
                if current and len(candidate) > max_chunk_chars:
                    chunks.append(current)
                    current = sentence
                else:
                    current = candidate
            if current:
                chunks.append(current)
        return chunks or [self._trim_text(text, max_chunk_chars)]

    def _extract_context_tokens(self, text: str) -> list[str]:
        tokens: list[str] = []
        seen: set[str] = set()
        for token in re.findall(
            r"[\u4e00-\u9fff]{2,}|[A-Za-z][A-Za-z0-9_-]{2,}|\d{2,}", text or ""
        ):
            normalized = token.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            tokens.append(normalized)
        return tokens

    def _score_supporting_chunk(
        self, query_text: str, query_tokens: list[str], chunk: str
    ) -> float:
        chunk_text = (chunk or "").strip()
        if not chunk_text:
            return 0.0
        lowered = chunk_text.lower()
        token_score = 0.0
        for token in query_tokens:
            if token in lowered:
                token_score += 2.0 if len(token) >= 4 else 1.0
        similarity = SequenceMatcher(None, query_text.lower()[:240], lowered[:480]).ratio()
        heading_bonus = 1.0 if chunk_text.lstrip().startswith("#") else 0.0
        return token_score + similarity * 6.0 + heading_bonus

    def _trim_text(self, value: str, max_chars: int) -> str:
        text = (value or "").strip()
        if len(text) <= max_chars:
            return text
        return text[: max_chars - 1].rstrip() + "…"
