#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Language helpers for question generation flows.
"""

from __future__ import annotations

import re
from typing import Iterable

from src.services.config import parse_language

_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
_LATIN_RE = re.compile(r"[A-Za-z]")

_LANGUAGE_LABELS = {
    "en": {"en": "English", "zh": "Chinese"},
    "zh": {"en": "英文", "zh": "中文"},
}


def _normalize_texts(input_texts: str | Iterable[str] | None) -> str:
    if input_texts is None:
        return ""

    if isinstance(input_texts, str):
        return input_texts.strip()

    return "\n".join(str(text).strip() for text in input_texts if text).strip()


def detect_input_language(input_texts: str | Iterable[str] | None) -> str | None:
    """
    Detect whether request text is dominantly Chinese or English.

    Detection is intentionally conservative:
    - Chinese needs at least 2 CJK chars and must dominate Latin letters
    - English needs at least 6 Latin letters and must dominate CJK chars
    - Low-signal or mixed text falls back to caller-supplied defaults
    """
    text = _normalize_texts(input_texts)
    if not text:
        return None

    cjk_count = len(_CJK_RE.findall(text))
    latin_count = len(_LATIN_RE.findall(text))

    if cjk_count >= 2 and cjk_count >= latin_count * 1.2:
        return "zh"

    if latin_count >= 6 and latin_count >= cjk_count * 1.2:
        return "en"

    return None


def resolve_output_language(
    input_texts: str | Iterable[str] | None,
    fallback_output_language: str | None = None,
    system_language: str = "zh",
) -> str:
    """
    Resolve final output language for a question-generation request.
    """
    detected_language = detect_input_language(input_texts)
    if detected_language:
        return detected_language

    if fallback_output_language:
        return parse_language(fallback_output_language)

    return parse_language(system_language)


def get_language_label(language: str, prompt_language: str | None = None) -> str:
    """
    Return a human-friendly language label in the prompt's language.
    """
    lang_code = parse_language(language)
    prompt_lang = parse_language(prompt_language or lang_code)
    return _LANGUAGE_LABELS[prompt_lang][lang_code]
