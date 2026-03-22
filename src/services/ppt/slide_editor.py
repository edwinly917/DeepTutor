from __future__ import annotations

from typing import Any, Callable

from src.services.ppt.prompts import PptPromptManager


class SlideEditor:
    def __init__(self, json_complete: Callable[[str, str], dict[str, Any]]):
        self.json_complete = json_complete

    def classify_edit(self, page: dict[str, Any], user_message: str) -> str:
        lowered = user_message.lower()
        image_keywords = ["图片", "配图", "图像", "视觉", "插画", "照片", "背景", "image", "visual"]
        outline_keywords = ["标题", "要点", "结构", "顺序", "大纲", "分成", "合并", "outline"]
        description_keywords = [
            "描述",
            "文案",
            "内容",
            "表述",
            "展开",
            "精简",
            "润色",
            "description",
        ]
        if any(keyword in lowered for keyword in image_keywords):
            return "image_edit"
        if any(keyword in lowered for keyword in outline_keywords):
            return "outline_edit"
        if any(keyword in lowered for keyword in description_keywords):
            return "description_edit"

        outline = page.get("outline_content") or {}
        system_prompt, user_prompt = PptPromptManager.chat_edit_classifier(
            slide_title=outline.get("title") or "Untitled",
            slide_points=outline.get("points") or [],
            user_message=user_message,
        )
        data = self.json_complete(user_prompt, system_prompt)
        edit_type = (data.get("edit_type") or "").strip()
        return (
            edit_type
            if edit_type in {"outline_edit", "description_edit", "image_edit"}
            else "description_edit"
        )

    def rewrite_outline(self, page: dict[str, Any], user_message: str) -> dict[str, Any]:
        outline = page.get("outline_content") or {}
        system_prompt, user_prompt = PptPromptManager.rewrite_outline(
            current_title=outline.get("title") or "Untitled",
            current_points=outline.get("points") or [],
            user_message=user_message,
        )
        data = self.json_complete(user_prompt, system_prompt)
        points = [str(point).strip() for point in (data.get("points") or []) if str(point).strip()]
        if not points:
            points = outline.get("points") or []
        title = (data.get("title") or "").strip() or outline.get("title") or "Untitled Slide"
        assistant_message = (
            data.get("assistant_message") or ""
        ).strip() or "已根据你的要求调整这一页的大纲，并开始重生成。"
        return {"title": title, "points": points, "assistant_message": assistant_message}

    def rewrite_description(self, page: dict[str, Any], user_message: str) -> dict[str, Any]:
        outline = page.get("outline_content") or {}
        current_description = (
            (page.get("description_content") or {}).get("text")
            if isinstance(page.get("description_content"), dict)
            else ""
        )
        system_prompt, user_prompt = PptPromptManager.rewrite_description(
            slide_title=outline.get("title") or "Untitled",
            slide_points=outline.get("points") or [],
            current_description=current_description or "",
            user_message=user_message,
        )
        data = self.json_complete(user_prompt, system_prompt)
        description_text = (data.get("description_text") or "").strip()
        if not description_text:
            raise ValueError("Failed to derive updated description text from chat instruction")
        assistant_message = (
            data.get("assistant_message") or ""
        ).strip() or "已根据你的要求改写这一页内容，并开始重生成。"
        return {
            "description_text": description_text,
            "assistant_message": assistant_message,
        }

    def rewrite_image_prompt(self, page: dict[str, Any], user_message: str) -> dict[str, Any]:
        outline = page.get("outline_content") or {}
        current_prompt = (page.get("image_prompt") or "").strip()
        system_prompt, user_prompt = PptPromptManager.rewrite_image_prompt(
            slide_title=outline.get("title") or "Untitled",
            slide_points=outline.get("points") or [],
            current_prompt=current_prompt,
            user_message=user_message,
        )
        data = self.json_complete(user_prompt, system_prompt)
        image_prompt = (data.get("image_prompt") or "").strip() or current_prompt
        if not image_prompt:
            raise ValueError("Failed to derive updated image prompt from chat instruction")
        assistant_message = (
            data.get("assistant_message") or ""
        ).strip() or "已根据你的要求调整图片方向，并开始重生成。"
        return {
            "image_prompt": image_prompt,
            "assistant_message": assistant_message,
        }
