"""
Helpers for cleaning extracted document text before UTF-8 dependent storage.
"""

from __future__ import annotations

import unicodedata


def sanitize_extracted_text(text: str) -> str:
    """Repair broken surrogate pairs and drop unsafe control characters.

    Some PDF extractors emit lone surrogate code points. Those cannot be encoded
    as UTF-8 and will later break LightRAG insertion or JSON writes. This helper
    repairs valid surrogate pairs into real Unicode scalars and replaces broken
    ones with the Unicode replacement character.
    """

    if not text:
        return ""

    repaired = text.encode("utf-16", "surrogatepass").decode("utf-16", "replace")

    cleaned_chars: list[str] = []
    for char in repaired:
        if char in "\n\r\t":
            cleaned_chars.append(char)
            continue

        if unicodedata.category(char) == "Cc":
            continue

        cleaned_chars.append(char)

    return "".join(cleaned_chars)
