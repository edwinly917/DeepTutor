from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

from src.services.storage import ppt_store


class SmartMerge:
    def __init__(self, default_layout):
        self.default_layout = default_layout

    def merge(
        self, project_id: str, existing_pages: list[dict[str, Any]], slides: list[dict[str, Any]]
    ) -> None:
        used_ids: set[str] = set()
        survivors: set[str] = set()
        for index, slide in enumerate(slides):
            matched = self.match_page(existing_pages, slide, index, used_ids)
            fields = {
                "order_index": index,
                "part": slide.get("part"),
                "outline_content": {
                    "title": slide.get("title") or f"Slide {index + 1}",
                    "points": slide.get("points") or [],
                    "layout": slide.get("layout") or self.default_layout(index),
                },
                "image_prompt": slide.get("imagePrompt"),
            }
            if matched:
                survivors.add(matched["id"])
                used_ids.add(matched["id"])
                ppt_store.update_page(matched["id"], **fields)
            else:
                page = ppt_store.create_page(
                    project_id=project_id,
                    order_index=index,
                    part=slide.get("part"),
                    outline_content=fields["outline_content"],
                    image_prompt=fields["image_prompt"],
                    status="DRAFT",
                )
                survivors.add(page["id"])

        stale_ids = [page["id"] for page in existing_pages if page["id"] not in survivors]
        ppt_store.delete_pages(stale_ids)

    def match_page(
        self,
        existing_pages: list[dict[str, Any]],
        slide: dict[str, Any],
        order_index: int,
        used_ids: set[str],
    ) -> dict[str, Any] | None:
        new_title = (slide.get("title") or "").strip().lower()
        exact = next(
            (
                page
                for page in existing_pages
                if page["id"] not in used_ids
                and (page.get("outline_content", {}).get("title") or "").strip().lower()
                == new_title
            ),
            None,
        )
        if exact:
            return exact

        best_match = None
        best_ratio = 0.0
        for page in existing_pages:
            if page["id"] in used_ids:
                continue
            old_title = (page.get("outline_content", {}).get("title") or "").strip().lower()
            ratio = SequenceMatcher(None, old_title, new_title).ratio()
            if page.get("order_index") == order_index:
                ratio += 0.1
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = page
        return best_match if best_ratio >= 0.55 else None
