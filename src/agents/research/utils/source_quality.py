#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Source quality utilities for research citations.
"""

from __future__ import annotations

import json
import re
from typing import Any

_UNINFORMATIVE_PATTERNS = [
    re.compile(r"没有足够的信息", re.IGNORECASE),
    re.compile(r"未找到[^。\n]*相关信息", re.IGNORECASE),
    re.compile(r"无法[^。\n]*回答", re.IGNORECASE),
    re.compile(r"no\s+relevant", re.IGNORECASE),
    re.compile(r"not\s+enough\s+information", re.IGNORECASE),
    re.compile(r"insufficient\s+information", re.IGNORECASE),
    re.compile(r"unable\s+to\s+answer", re.IGNORECASE),
    re.compile(r"no\s+relevant\s+references\s+found", re.IGNORECASE),
]


def _parse_answer(raw_answer: Any) -> dict[str, Any]:
    if isinstance(raw_answer, dict):
        return raw_answer
    if isinstance(raw_answer, str):
        try:
            parsed = json.loads(raw_answer)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


def _is_non_empty_item(item: Any) -> bool:
    if isinstance(item, dict):
        return any(
            str(item.get(key, "")).strip()
            for key in (
                "title",
                "url",
                "content",
                "content_preview",
                "source",
                "source_file",
                "identifier",
            )
        )
    return bool(str(item).strip())


def extract_source_count(tool_type: str, raw_answer: Any) -> int:
    """
    Count source-like items from tool output payload.
    """
    tool = (tool_type or "").lower()
    data = _parse_answer(raw_answer)

    if tool in ("rag_naive", "rag_hybrid", "query_item"):
        for field in ("sources", "chunks", "documents", "context", "retrieved_docs", "items"):
            value = data.get(field)
            if isinstance(value, list):
                return len([item for item in value if _is_non_empty_item(item)])
        count = data.get("count")
        if isinstance(count, int) and count >= 0:
            return count
        return 0

    if tool == "web_search":
        for field in (
            "web_sources",
            "citations",
            "references",
            "results",
            "web_results",
            "search_results",
            "urls",
        ):
            value = data.get(field)
            if isinstance(value, list):
                return len([item for item in value if _is_non_empty_item(item)])
        if str(data.get("url", "")).strip():
            return 1
        return 0

    if tool == "paper_search":
        papers = data.get("papers")
        if isinstance(papers, list):
            return len([item for item in papers if _is_non_empty_item(item)])
        return 0

    return 0


def is_uninformative_result(tool_type: str, raw_answer: Any, summary: str = "") -> bool:
    """
    Check whether a tool result is effectively non-informative.
    """
    data = _parse_answer(raw_answer)
    status = str(data.get("status", "")).lower()
    if status in ("failed", "error"):
        return True
    if data.get("error"):
        return True

    if extract_source_count(tool_type, raw_answer) > 0:
        return False

    text_parts = [
        str(summary or ""),
        str(data.get("answer", "") or ""),
        str(data.get("content", "") or ""),
        str(raw_answer or "") if isinstance(raw_answer, str) else "",
    ]
    merged = "\n".join([part for part in text_parts if part]).strip()
    if not merged:
        return True

    return any(pattern.search(merged) for pattern in _UNINFORMATIVE_PATTERNS)
