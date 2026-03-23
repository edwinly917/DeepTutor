from __future__ import annotations

import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import re
from typing import Any
import uuid

from PIL import Image

from src.logging import get_logger
from src.services.config import get_banana_ppt_config, load_config_with_main
from src.services.export.ppt_task_manager import ppt_task_manager
from src.services.llm import complete as llm_complete
from src.services.llm import get_llm_config, get_token_limit_kwargs
from src.services.ppt.content_extractors import (
    NotebookExtractor,
    ResearchExtractor,
    SourcesExtractor,
)
from src.services.ppt.description_generator import DescriptionGenerator
from src.services.ppt.export_service import PptExportService
from src.services.ppt.image_generator import ImageGenerator
from src.services.ppt.outline_generator import OutlineGenerator
from src.services.ppt.preset_styles import DEFAULT_PRESET_STYLE_ID
from src.services.ppt.prompts import PptPromptManager, StyleContext
from src.services.ppt.slide_editor import SlideEditor
from src.services.ppt.smart_merge import SmartMerge
from src.services.ppt.template_analyzer import TemplateAnalyzer
from src.services.storage import ppt_store

logger = get_logger("PPTProjectService")
_REFERENCE_IMAGE_MAX_BYTES = 10 * 1024 * 1024
_REFERENCE_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

_LAYOUT_SEQUENCE = [
    "SECTION_HEADER",
    "SPLIT_IMAGE_RIGHT",
    "TOP_IMAGE",
    "SPLIT_IMAGE_LEFT",
    "TYPOGRAPHIC_WITH_IMAGE",
    "OVERVIEW",
    "QUOTE",
    "TYPOGRAPHIC",
]

_ACTIVE_TASK_STATUSES = {"PENDING", "RUNNING"}
_PROJECT_LEVEL_TASK_TYPES = {"GENERATE_DESCRIPTIONS", "GENERATE_IMAGES", "GENERATE_FULL"}
_PAGE_LEVEL_TASK_TYPES = {"REGENERATE_PAGE_IMAGE", "PAGE_CHAT_EDIT"}
_SUPPORTED_CREATION_TYPES = {
    "from_research",
    "from_notebook",
    "from_sources",
}


@dataclass
class _TaskProgress:
    current: int
    total: int
    percentage: int
    message: str
    warnings: list[str]
    failed_count: int
    download_url: str | None = None
    page_ids: list[str] | None = None
    phase: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "current": self.current,
            "total": self.total,
            "percentage": self.percentage,
            "message": self.message,
            "warnings": self.warnings,
            "failed_count": self.failed_count,
            "download_url": self.download_url,
            "page_ids": self.page_ids or [],
            "phase": self.phase,
        }


class ReferenceImageValidationError(ValueError):
    pass


class ReferenceStyleExtractionError(ValueError):
    pass


class PptProjectService:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.config = load_config_with_main("main.yaml", project_root)
        export_cfg = self.config.get("export", {}) or {}
        self.ppt_v2_config = export_cfg.get("ppt_v2", {}) or {}
        self.banana_config = get_banana_ppt_config(project_root)
        self.outline_generator = OutlineGenerator(project_root)
        self.image_generator = ImageGenerator(project_root)
        self.export_service = PptExportService(project_root)
        self.research_extractor = ResearchExtractor()
        self.notebook_extractor = NotebookExtractor()
        self.sources_extractor = SourcesExtractor()
        self.description_generator = DescriptionGenerator(self._complete_json_sync)
        self.slide_editor = SlideEditor(self._complete_json_sync)
        self.smart_merge = SmartMerge(self._default_layout)
        self.template_analyzer = TemplateAnalyzer(project_root)
        task_cfg = self.ppt_v2_config.get("task", {}) or {}
        self.description_workers = int(task_cfg.get("description_workers", 4))
        self.image_workers = int(task_cfg.get("image_workers", 3))
        self.polling_hint_ms = int(task_cfg.get("polling_hint_ms", 1500))

    def get_config(self) -> dict[str, Any]:
        return {
            "enabled": self.ppt_v2_config.get("enabled", True),
            "max_slides": int(
                self.ppt_v2_config.get(
                    "max_slides",
                    self.banana_config.max_slides
                    or (self.config.get("export", {}).get("ppt", {}) or {}).get("max_slides", 15),
                )
            ),
            "style_presets": PptPromptManager.list_style_presets(),
            "polling_hint_ms": self.polling_hint_ms,
            "creation_modes": ["auto", "from_research", "from_notebook", "from_sources"],
        }

    def create_project(
        self,
        *,
        notebook_id: str | None,
        session_id: str | None,
        creation_type: str,
        source_content: str | None,
        style_preset_id: str | None,
        style_custom_text: str | None,
        template_image_path: str | None,
        template_file_refs: list[dict[str, Any]] | None,
        reference_style_prompt: str | None,
        reference_layout_prompt: str | None,
        reference_content_prompt: str | None,
        image_aspect_ratio: str,
        language: str,
        reference_sources: list[dict[str, Any]] | None,
        source_refs: list[dict[str, Any]] | None = None,
        record_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        if creation_type not in _SUPPORTED_CREATION_TYPES:
            raise ValueError("Invalid creation_type")
        if image_aspect_ratio not in {"16:9", "4:3"}:
            raise ValueError("Invalid image_aspect_ratio")
        frozen_source_content = (source_content or "").strip() or None
        frozen_source_refs = [dict(item) for item in (source_refs or reference_sources or [])]
        normalized_content: str | None = None

        if creation_type == "from_research":
            frozen_source_content, frozen_source_refs = (
                self.research_extractor.freeze_project_input(
                    notebook_id=notebook_id,
                    session_id=session_id,
                    source_content=frozen_source_content,
                    source_refs=frozen_source_refs,
                )
            )
        elif creation_type == "from_notebook":
            frozen_source_content = (
                frozen_source_content
                or self.notebook_extractor.freeze_project_input(
                    notebook_id=notebook_id,
                    record_ids=record_ids or [],
                )
            )
        elif creation_type == "from_sources":
            if not frozen_source_refs:
                raise ValueError("source_refs are required for from_sources")

        project = ppt_store.create_project(
            notebook_id=notebook_id,
            session_id=session_id,
            creation_type=creation_type,
            idea_prompt=None,
            outline_text=None,
            description_text=None,
            source_content=frozen_source_content,
            style_preset_id=(style_preset_id or DEFAULT_PRESET_STYLE_ID).strip()
            or DEFAULT_PRESET_STYLE_ID,
            style_custom_text=(style_custom_text or "").strip() or None,
            template_image_path=(template_image_path or "").strip() or None,
            template_file_refs=[dict(item) for item in (template_file_refs or [])],
            reference_style_prompt=(reference_style_prompt or "").strip() or None,
            reference_layout_prompt=(reference_layout_prompt or "").strip() or None,
            reference_content_prompt=(reference_content_prompt or "").strip() or None,
            image_aspect_ratio=image_aspect_ratio,
            language=language or "zh",
            reference_sources=reference_sources or [],
            source_refs=frozen_source_refs,
            record_ids=record_ids or [],
            normalized_content=normalized_content,
            status="DRAFT",
        )
        return self.get_project_bundle(project["id"])

    def get_project_bundle(self, project_id: str) -> dict[str, Any] | None:
        bundle = ppt_store.get_project_bundle(project_id)
        if not bundle:
            return None
        bundle["presentation_outline"] = self._project_to_presentation_outline(bundle)
        return bundle

    async def upload_reference_image(
        self,
        *,
        filename: str,
        content_type: str | None,
        data: bytes,
    ) -> dict[str, Any]:
        safe_name = Path(filename or "reference-image.png").name
        suffix = Path(safe_name).suffix.lower()
        if suffix not in _REFERENCE_IMAGE_EXTENSIONS:
            raise ReferenceImageValidationError("Only png, jpg, jpeg, and webp are supported")
        if not data:
            raise ReferenceImageValidationError("Reference image is empty")
        if len(data) > _REFERENCE_IMAGE_MAX_BYTES:
            raise ReferenceImageValidationError("Reference image exceeds 10MB limit")
        try:
            image = Image.open(io.BytesIO(data))
            image.verify()
        except Exception as exc:
            raise ReferenceImageValidationError("Invalid reference image file") from exc

        output_dir = self.project_root / "data" / "user" / "ppt" / "reference_images"
        output_dir.mkdir(parents=True, exist_ok=True)
        stem = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(safe_name).stem).strip("-") or "reference"
        stored_name = f"{uuid.uuid4().hex[:12]}_{stem}{suffix}"
        output_path = output_dir / stored_name
        output_path.write_bytes(data)

        try:
            analysis = await self.template_analyzer.analyze_path(output_path)
        except Exception as exc:
            output_path.unlink(missing_ok=True)
            raise ReferenceStyleExtractionError(str(exc)) from exc

        relative_path = self._to_output_relative(output_path)
        return {
            "image_path": relative_path,
            "image_url": self._to_output_url(relative_path),
            "image_name": safe_name,
            "derived_style_prompt": analysis.reference_style_prompt,
            "derived_layout_prompt": analysis.reference_layout_prompt,
            "derived_content_prompt": analysis.reference_content_prompt,
            "content_type": content_type or self._guess_image_content_type(output_path),
        }

    async def preview_style(
        self,
        *,
        style_preset_id: str | None = None,
        style_custom_text: str | None = None,
        reference_style_prompt: str | None = None,
        reference_layout_prompt: str | None = None,
        reference_content_prompt: str | None = None,
        language: str = "zh",
    ) -> dict[str, Any]:
        style_context = self._build_style_context(
            style_preset_id=style_preset_id,
            style_custom_text=style_custom_text,
            reference_style_prompt=reference_style_prompt,
            reference_layout_prompt=reference_layout_prompt,
            reference_content_prompt=reference_content_prompt,
        )
        theme = self._build_style_preview_theme(style_context.preview_prompt(language))
        payload = PptPromptManager.style_context_to_preview_payload(style_context, language)
        return {"theme": theme, "preview_svg": self._build_style_preview_svg(theme), **payload}

    async def generate_image_preview(
        self,
        *,
        prompt: str,
        slide_title: str | None = None,
        slide_points: list[str] | None = None,
        layout: str | None = None,
        deck_title: str | None = None,
        style_prompt: str | None = None,
    ) -> dict[str, Any]:
        image_data_url = await self.image_generator.generate_image(
            prompt=prompt,
            slide_title=slide_title,
            slide_points=slide_points,
            layout=layout,
            deck_title=deck_title,
            style_prompt=style_prompt,
        )
        return {"image_data_url": image_data_url}

    async def generate_outline(
        self,
        project_id: str,
        *,
        max_slides: int | None = None,
    ) -> dict[str, Any]:
        project = ppt_store.get_project(project_id)
        if not project:
            raise ValueError("Project not found")
        project = await self._ensure_template_analysis(project)
        project, _ = await self._prepare_project_source_content(project_id, project)

        normalized_outline = await self._build_outline(project, max_slides=max_slides)
        existing_pages = ppt_store.list_pages(project_id)
        self._smart_merge_pages(project_id, existing_pages, normalized_outline["slides"])
        ppt_store.update_project(
            project_id,
            status="OUTLINE_GENERATED",
        )
        bundle = self.get_project_bundle(project_id)
        if not bundle:
            raise ValueError("Project not found after outline generation")
        return bundle

    def start_generate_descriptions(
        self,
        project_id: str,
        *,
        page_ids: list[str] | None = None,
        detail_level: str = "default",
    ) -> dict[str, Any]:
        project = ppt_store.get_project(project_id)
        if not project:
            raise ValueError("Project not found")
        self._assert_no_active_project_task(project_id)
        pages = self._filter_pages(project_id, page_ids)
        if not pages:
            raise ValueError("No pages available for description generation")
        progress = self._build_progress(
            0,
            len(pages),
            "等待生成页面描述",
            failed_count=0,
            page_ids=[page["id"] for page in pages],
        )
        task = ppt_store.create_task(project_id, "GENERATE_DESCRIPTIONS", progress=progress)
        for page in pages:
            ppt_store.update_page(page["id"], status="DESCRIPTION_QUEUED")
        ppt_store.update_project(project_id, status="DESCRIPTIONS_GENERATING")
        ppt_task_manager.submit(
            task["id"], self._run_generate_descriptions, project_id, page_ids or [], detail_level
        )
        return task

    def start_generate_images(
        self,
        project_id: str,
        *,
        page_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        project = ppt_store.get_project(project_id)
        if not project:
            raise ValueError("Project not found")
        self._assert_no_active_project_task(project_id)
        pages = self._filter_pages(project_id, page_ids)
        if not pages:
            raise ValueError("No pages available for image generation")
        progress = self._build_progress(
            0,
            len(pages),
            "等待生成页面图片",
            failed_count=0,
            page_ids=[page["id"] for page in pages],
        )
        task = ppt_store.create_task(project_id, "GENERATE_IMAGES", progress=progress)
        for page in pages:
            ppt_store.update_page(page["id"], status="IMAGE_QUEUED")
        ppt_store.update_project(project_id, status="IMAGES_GENERATING")
        ppt_task_manager.submit(task["id"], self._run_generate_images, project_id, page_ids or [])
        return task

    def start_generate_full(
        self,
        project_id: str,
        *,
        max_slides: int | None = None,
        detail_level: str = "default",
    ) -> dict[str, Any]:
        project = ppt_store.get_project(project_id)
        if not project:
            raise ValueError("Project not found")
        self._assert_no_active_project_task(project_id)
        progress = self._build_progress(
            0,
            3,
            "等待开始完整 PPT 生成",
            failed_count=0,
            phase="prepare",
        )
        task = ppt_store.create_task(project_id, "GENERATE_FULL", progress=progress)
        ppt_task_manager.submit(
            task["id"],
            self._run_generate_full,
            project_id,
            max_slides,
            detail_level,
        )
        return task

    def get_task(self, project_id: str, task_id: str) -> dict[str, Any] | None:
        return ppt_store.get_task(project_id, task_id)

    def list_slide_chat_history(self, project_id: str, page_id: str) -> list[dict[str, Any]]:
        page = ppt_store.get_page(page_id)
        if not page or page["project_id"] != project_id:
            raise ValueError("Page not found")
        return ppt_store.list_slide_chat_messages(page_id)

    def start_page_chat_edit(
        self,
        project_id: str,
        page_id: str,
        *,
        message: str,
    ) -> dict[str, Any]:
        page = ppt_store.get_page(page_id)
        if not page or page["project_id"] != project_id:
            raise ValueError("Page not found")
        user_message = (message or "").strip()
        if not user_message:
            raise ValueError("message is empty")
        self._assert_page_regeneration_allowed(project_id, page_id)
        project = ppt_store.get_project(project_id)
        if not project:
            raise ValueError("Project not found")

        edit_type = self._classify_page_chat_edit(project, page, user_message)
        assistant_message: str
        if edit_type == "outline_edit":
            updated_outline = self._rewrite_outline_from_chat(project, page, user_message)
            assistant_message = updated_outline.pop("assistant_message")
            page = self.update_page(
                project_id,
                page_id,
                title=updated_outline["title"],
                points=updated_outline["points"],
            )
        elif edit_type == "description_edit":
            updated_description = self._rewrite_description_from_chat(project, page, user_message)
            assistant_message = updated_description.pop("assistant_message")
            page = self.update_page(
                project_id,
                page_id,
                description_text=updated_description["description_text"],
            )
        else:
            updated_image = self._rewrite_image_prompt_from_chat(project, page, user_message)
            assistant_message = updated_image.pop("assistant_message")
            page = self.update_page(
                project_id,
                page_id,
                image_prompt=updated_image["image_prompt"],
            )

        ppt_store.create_slide_chat_message(
            page_id=page_id,
            role="user",
            content=user_message,
            edit_type=edit_type,
        )
        ppt_store.create_slide_chat_message(
            page_id=page_id,
            role="assistant",
            content=assistant_message,
            edit_type=edit_type,
        )

        total_steps = 1 if edit_type == "image_edit" else 2
        task = ppt_store.create_task(
            project_id,
            "PAGE_CHAT_EDIT",
            progress=self._build_progress(
                0,
                total_steps,
                "等待根据对话修改页面",
                failed_count=0,
                page_ids=[page_id],
                phase="prepare",
            ),
        )
        ppt_task_manager.submit(
            task["id"], self._run_page_chat_edit, project_id, page_id, edit_type
        )
        return {
            "task": task,
            "edit_type": edit_type,
            "assistant_message": assistant_message,
            "page": page,
        }

    def update_page(
        self,
        project_id: str,
        page_id: str,
        *,
        title: str | None = None,
        points: list[str] | None = None,
        description_text: str | None = None,
        image_prompt: str | None = None,
    ) -> dict[str, Any]:
        page = ppt_store.get_page(page_id)
        if not page or page["project_id"] != project_id:
            raise ValueError("Page not found")
        if title is None and points is None and description_text is None and image_prompt is None:
            return page

        outline_content = dict(page["outline_content"] or {})
        if title is not None:
            outline_content["title"] = title.strip()
        if points is not None:
            outline_content["points"] = [
                str(point).strip() for point in points if str(point).strip()
            ]

        description_content = page.get("description_content")
        if description_text is not None:
            description_content = {
                "text": description_text.strip(),
                "generated_at": description_content.get("generated_at")
                if isinstance(description_content, dict)
                else None,
                "detail_level": description_content.get("detail_level")
                if isinstance(description_content, dict)
                else None,
            }

        updated = ppt_store.update_page(
            page_id,
            outline_content=outline_content,
            description_content=description_content,
            image_prompt=image_prompt if image_prompt is not None else page.get("image_prompt"),
            is_dirty=True,
            status="DRAFT",
        )
        if not updated:
            raise ValueError("Failed to update page")
        return updated

    def list_image_versions(self, project_id: str, page_id: str) -> list[dict[str, Any]]:
        page = ppt_store.get_page(page_id)
        if not page or page["project_id"] != project_id:
            raise ValueError("Page not found")
        return ppt_store.list_page_image_versions(page_id)

    def activate_image_version(
        self, project_id: str, page_id: str, version_number: int
    ) -> dict[str, Any]:
        page = ppt_store.get_page(page_id)
        if not page or page["project_id"] != project_id:
            raise ValueError("Page not found")
        version = ppt_store.activate_page_image_version(page_id, version_number)
        if not version:
            raise ValueError("Image version not found")
        ppt_store.update_page(
            page_id,
            generated_image_path=version["image_path"],
            cached_image_path=version.get("cached_image_path"),
            status="IMAGE_READY",
        )
        return version

    def start_regenerate_page_image(self, project_id: str, page_id: str) -> dict[str, Any]:
        page = ppt_store.get_page(page_id)
        if not page or page["project_id"] != project_id:
            raise ValueError("Page not found")
        self._assert_page_regeneration_allowed(project_id, page_id)
        requires_full_regeneration = bool(page.get("is_dirty")) or page.get("status") in {
            "DRAFT",
            "DESCRIPTION_QUEUED",
            "DESCRIPTION_GENERATING",
            "DESCRIPTION_READY",
        }
        total_steps = 2 if requires_full_regeneration else 1
        progress = self._build_progress(
            0,
            total_steps,
            "等待重生成页面",
            failed_count=0,
            page_ids=[page_id],
        )
        task = ppt_store.create_task(project_id, "REGENERATE_PAGE_IMAGE", progress=progress)
        if requires_full_regeneration:
            ppt_store.update_page(page_id, status="DESCRIPTION_QUEUED", is_dirty=True)
        else:
            ppt_store.update_page(page_id, status="IMAGE_QUEUED", is_dirty=True)
        ppt_task_manager.submit(
            task["id"],
            self._run_page_regeneration,
            project_id,
            page_id,
            requires_full_regeneration,
        )
        return task

    def export_pptx(self, project_id: str, page_ids: list[str] | None = None) -> dict[str, Any]:
        return self.export_pptx_with_title(project_id, page_ids=page_ids)

    def export_pptx_with_title(
        self,
        project_id: str,
        *,
        page_ids: list[str] | None = None,
        title_override: str | None = None,
    ) -> dict[str, Any]:
        project = self.get_project_bundle(project_id)
        if not project:
            raise ValueError("Project not found")
        self._assert_no_active_export_conflict(project_id, page_ids)
        pages = self._filter_pages(project_id, page_ids)
        if any(page.get("is_dirty") for page in pages):
            raise ValueError("Some slides are pending regeneration and cannot be exported")
        image_paths = self._collect_image_paths(pages)
        if not image_paths:
            raise ValueError("No generated images available for PPT export")
        if len(image_paths) != len(pages):
            raise ValueError("Some slides are missing generated images")
        title = (title_override or "").strip() or self._resolve_project_title(project)
        return self.export_service.export_pptx(
            project_id=project_id,
            title=title,
            image_paths=image_paths,
            aspect_ratio=project.get("image_aspect_ratio") or "16:9",
        )

    def export_pdf(self, project_id: str, page_ids: list[str] | None = None) -> dict[str, Any]:
        return self.export_pdf_with_title(project_id, page_ids=page_ids)

    def export_pdf_with_title(
        self,
        project_id: str,
        *,
        page_ids: list[str] | None = None,
        title_override: str | None = None,
    ) -> dict[str, Any]:
        project = self.get_project_bundle(project_id)
        if not project:
            raise ValueError("Project not found")
        self._assert_no_active_export_conflict(project_id, page_ids)
        pages = self._filter_pages(project_id, page_ids)
        if any(page.get("is_dirty") for page in pages):
            raise ValueError("Some slides are pending regeneration and cannot be exported")
        image_paths = self._collect_image_paths(pages)
        if not image_paths:
            raise ValueError("No generated images available for PDF export")
        if len(image_paths) != len(pages):
            raise ValueError("Some slides are missing generated images")
        title = (title_override or "").strip() or self._resolve_project_title(project)
        return self.export_service.export_pdf(
            project_id=project_id, title=title, image_paths=image_paths
        )

    async def _build_outline(
        self,
        project: dict[str, Any],
        *,
        max_slides: int | None,
    ) -> dict[str, Any]:
        limit = int(max_slides or self.get_config()["max_slides"])
        style_context = self._style_context_for_project(project)
        source_brief = (project.get("normalized_content") or "").strip()
        if not source_brief:
            raise ValueError("No project source content available for outline generation")
        outline = await self.outline_generator.generate_outline(
            source_content=source_brief,
            style_context=style_context,
            max_slides=limit,
            language=project.get("language") or "zh",
            source_type=project.get("creation_type") or "from_sources",
            reference_files=project.get("template_file_refs") or [],
        )
        for index, slide in enumerate(outline.get("slides") or []):
            slide.setdefault("layout", self._default_layout(index))
        return outline

    async def _prepare_project_source_content(
        self, project_id: str, project: dict[str, Any]
    ) -> tuple[dict[str, Any], list[str]]:
        creation_type = project.get("creation_type")
        if creation_type not in {"from_research", "from_notebook", "from_sources"}:
            return project, []

        warnings: list[str] = []

        if creation_type == "from_research":
            source_content, source_refs = self.research_extractor.freeze_project_input(
                notebook_id=project.get("notebook_id"),
                session_id=project.get("session_id"),
                source_content=project.get("source_content"),
                source_refs=project.get("source_refs") or project.get("reference_sources") or [],
            )
            project = (
                ppt_store.update_project(
                    project_id,
                    source_content=source_content,
                    source_refs=source_refs,
                )
                or project
            )
        elif creation_type == "from_notebook":
            if not project.get("source_content"):
                source_content = self.notebook_extractor.freeze_project_input(
                    notebook_id=project.get("notebook_id"),
                    record_ids=project.get("record_ids") or [],
                )
                project = ppt_store.update_project(project_id, source_content=source_content) or project
        elif creation_type == "from_sources" and not project.get("source_content"):
            source_refs = project.get("source_refs") or project.get("reference_sources") or []
            if not source_refs:
                raise ValueError("from_sources requires frozen source_refs")
            markdown, warnings, cached_at = await self.sources_extractor.generate_markdown(
                source_refs=source_refs,
                topic=self._resolve_project_topic(project) or None,
            )
            project = (
                ppt_store.update_project(
                    project_id,
                    source_content=markdown,
                    content_cached_at=cached_at,
                )
                or project
            )

        normalized_content = (project.get("normalized_content") or "").strip()
        if not normalized_content:
            source_content = (project.get("source_content") or "").strip()
            if not source_content:
                raise ValueError("No source content available for PPT normalization")
            normalized_content = await self._normalize_to_deck_source_brief(project, source_content)
            project = (
                ppt_store.update_project(project_id, normalized_content=normalized_content) or project
            )
        return project, warnings

    def _smart_merge_pages(
        self, project_id: str, existing_pages: list[dict[str, Any]], slides: list[dict[str, Any]]
    ) -> None:
        self.smart_merge.merge(project_id, existing_pages, slides)

    def _run_generate_descriptions(
        self, task_id: str, project_id: str, page_ids: list[str], detail_level: str
    ) -> None:
        project = ppt_store.get_project(project_id)
        if not project:
            ppt_store.update_task(task_id, status="FAILED", error_message="Project not found")
            return
        project = asyncio.run(self._ensure_template_analysis(project))
        pages = self._filter_pages(project_id, page_ids or None)
        deck_pages = self._filter_pages(project_id, None)
        deck_outline_summary = self._build_deck_outline_summary(deck_pages)
        style_context = self._style_context_for_project(project)
        total = len(pages)
        ppt_store.update_task(
            task_id,
            status="RUNNING",
            progress=self._build_progress(
                0,
                total,
                "正在生成页面描述",
                failed_count=0,
                page_ids=[page["id"] for page in pages],
            ),
        )

        completed = 0
        failed = 0
        warnings: list[str] = []
        with ThreadPoolExecutor(max_workers=max(1, self.description_workers)) as executor:
            futures = {
                executor.submit(
                    self._generate_page_description,
                    project,
                    page,
                    detail_level,
                    deck_outline_summary,
                    style_context,
                ): page["id"]
                for page in pages
            }
            for future in as_completed(futures):
                page_id = futures[future]
                try:
                    payload = future.result()
                    ppt_store.update_page(
                        page_id,
                        description_content=payload["description_content"],
                        image_prompt=payload["image_prompt"],
                        status="DESCRIPTION_READY",
                    )
                    completed += 1
                except Exception as exc:
                    failed += 1
                    warnings.append(f"页面 {page_id} 描述生成失败: {exc}")
                    ppt_store.update_page(page_id, status="FAILED")
                progress = self._build_progress(
                    completed + failed,
                    total,
                    f"已完成 {completed + failed}/{total} 页描述",
                    warnings=warnings[-5:],
                    failed_count=failed,
                    page_ids=[page["id"] for page in pages],
                )
                ppt_store.update_task(task_id, status="RUNNING", progress=progress)

        ppt_store.update_project(project_id, status="DESCRIPTIONS_GENERATED")
        ppt_store.update_task(
            task_id,
            status="COMPLETED",
            progress=self._build_progress(
                total,
                total,
                "页面描述生成完成",
                warnings=warnings[-5:],
                failed_count=failed,
                page_ids=[page["id"] for page in pages],
            ),
            error_message=None,
        )

    def _generate_page_description(
        self,
        project: dict[str, Any],
        page: dict[str, Any],
        detail_level: str,
        deck_outline_summary: str,
        style_context: StyleContext,
    ) -> dict[str, Any]:
        ppt_store.update_page(page["id"], status="DESCRIPTION_GENERATING")
        payload = self.description_generator.generate_page_description(
            project,
            page,
            detail_level=detail_level,
            deck_outline_summary=deck_outline_summary,
            style_context=style_context,
        )
        payload["description_content"]["generated_at"] = datetime.now(timezone.utc).isoformat()
        if not payload.get("image_prompt"):
            outline = page.get("outline_content") or {}
            payload["image_prompt"] = self._fallback_image_prompt(
                outline.get("title") or "Untitled Slide",
                outline.get("points") or [],
            )
        return payload

    def _run_generate_images(self, task_id: str, project_id: str, page_ids: list[str]) -> None:
        project = ppt_store.get_project(project_id)
        if not project:
            ppt_store.update_task(task_id, status="FAILED", error_message="Project not found")
            return
        project = asyncio.run(self._ensure_template_analysis(project))
        pages = self._filter_pages(project_id, page_ids or None)
        deck_pages = self._filter_pages(project_id, None)
        deck_title = self._resolve_project_title({"pages": deck_pages, **project})
        style_context = self._style_context_for_project(project)
        total = len(pages)
        ppt_store.update_task(
            task_id,
            status="RUNNING",
            progress=self._build_progress(
                0,
                total,
                "正在生成页面图片",
                failed_count=0,
                page_ids=[page["id"] for page in pages],
            ),
        )

        completed = 0
        failed = 0
        warnings: list[str] = []
        with ThreadPoolExecutor(max_workers=max(1, self.image_workers)) as executor:
            futures = {
                executor.submit(self._generate_page_image, project, page, style_context, deck_title): page[
                    "id"
                ]
                for page in pages
            }
            for future in as_completed(futures):
                page_id = futures[future]
                try:
                    payload = future.result()
                    ppt_store.update_page(
                        page_id,
                        generated_image_path=payload["generated_image_path"],
                        cached_image_path=payload["cached_image_path"],
                        is_dirty=False,
                        status="IMAGE_READY",
                    )
                    version_number = ppt_store.get_next_page_image_version(page_id)
                    ppt_store.create_page_image_version(
                        page_id=page_id,
                        version_number=version_number,
                        image_path=payload["generated_image_path"],
                        cached_image_path=payload["cached_image_path"],
                        prompt_used=payload["prompt_used"],
                        is_current=True,
                    )
                    completed += 1
                except Exception as exc:
                    failed += 1
                    warnings.append(f"页面 {page_id} 图片生成失败: {exc}")
                    ppt_store.update_page(page_id, status="FAILED")
                progress = self._build_progress(
                    completed + failed,
                    total,
                    f"已完成 {completed + failed}/{total} 页图片",
                    warnings=warnings[-5:],
                    failed_count=failed,
                    page_ids=[page["id"] for page in pages],
                )
                ppt_store.update_task(task_id, status="RUNNING", progress=progress)

        ppt_store.update_project(project_id, status="COMPLETED")
        ppt_store.update_task(
            task_id,
            status="COMPLETED",
            progress=self._build_progress(
                total,
                total,
                "页面图片生成完成",
                warnings=warnings[-5:],
                failed_count=failed,
                page_ids=[page["id"] for page in pages],
            ),
            error_message=None,
        )

    def _run_generate_full(
        self,
        task_id: str,
        project_id: str,
        max_slides: int | None,
        detail_level: str,
    ) -> None:
        warnings: list[str] = []
        failed_count = 0
        try:
            project = ppt_store.get_project(project_id)
            if not project:
                raise ValueError("Project not found")

            ppt_store.update_task(
                task_id,
                status="RUNNING",
                progress=self._build_progress(
                    0,
                    3,
                    "正在准备生成输入",
                    failed_count=0,
                    phase="prepare",
                ),
            )
            project, prep_warnings = asyncio.run(
                self._prepare_project_source_content(project_id, project)
            )
            warnings.extend(prep_warnings)

            ppt_store.update_task(
                task_id,
                status="RUNNING",
                progress=self._build_progress(
                    0,
                    3,
                    "正在生成 PPT 大纲",
                    warnings=warnings[-5:],
                    failed_count=0,
                    phase="outline",
                ),
            )
            asyncio.run(
                self.generate_outline(project_id, max_slides=max_slides)
            )

            project = ppt_store.get_project(project_id) or project
            project = asyncio.run(self._ensure_template_analysis(project))
            pages = self._filter_pages(project_id, None)
            if not pages:
                raise ValueError("No pages available after outline generation")
            deck_pages = self._filter_pages(project_id, None)
            deck_outline_summary = self._build_deck_outline_summary(deck_pages)
            style_context = self._style_context_for_project(project)

            for page in pages:
                ppt_store.update_page(page["id"], status="DESCRIPTION_QUEUED", is_dirty=True)
            ppt_store.update_project(project_id, status="DESCRIPTIONS_GENERATING")
            total_pages = len(pages)
            ppt_store.update_task(
                task_id,
                status="RUNNING",
                progress=self._build_progress(
                    1,
                    3,
                    f"正在生成页面描述 0/{total_pages}",
                    warnings=warnings[-5:],
                    failed_count=failed_count,
                    page_ids=[page["id"] for page in pages],
                    phase="descriptions",
                ),
            )

            desc_completed = 0
            with ThreadPoolExecutor(max_workers=max(1, self.description_workers)) as executor:
                futures = {
                    executor.submit(
                        self._generate_page_description,
                        project,
                        page,
                        detail_level,
                        deck_outline_summary,
                        style_context,
                    ): page["id"]
                    for page in pages
                }
                for future in as_completed(futures):
                    page_id = futures[future]
                    try:
                        payload = future.result()
                        ppt_store.update_page(
                            page_id,
                            description_content=payload["description_content"],
                            image_prompt=payload["image_prompt"],
                            status="DESCRIPTION_READY",
                            is_dirty=True,
                        )
                        desc_completed += 1
                    except Exception as exc:
                        failed_count += 1
                        warnings.append(f"页面 {page_id} 描述生成失败: {exc}")
                        ppt_store.update_page(page_id, status="FAILED", is_dirty=True)
                    ppt_store.update_task(
                        task_id,
                        status="RUNNING",
                        progress=self._build_progress(
                            1,
                            3,
                            f"正在生成页面描述 {desc_completed + failed_count}/{total_pages}",
                            warnings=warnings[-5:],
                            failed_count=failed_count,
                            page_ids=[page["id"] for page in pages],
                            phase="descriptions",
                        ),
                    )

            ppt_store.update_project(project_id, status="DESCRIPTIONS_GENERATED")

            pages = self._filter_pages(project_id, None)
            deck_title = self._resolve_project_title({"pages": pages, **project})
            for page in pages:
                ppt_store.update_page(page["id"], status="IMAGE_QUEUED", is_dirty=True)
            ppt_store.update_project(project_id, status="IMAGES_GENERATING")
            ppt_store.update_task(
                task_id,
                status="RUNNING",
                progress=self._build_progress(
                    2,
                    3,
                    f"正在生成页面图片 0/{total_pages}",
                    warnings=warnings[-5:],
                    failed_count=failed_count,
                    page_ids=[page["id"] for page in pages],
                    phase="images",
                ),
            )

            image_completed = 0
            with ThreadPoolExecutor(max_workers=max(1, self.image_workers)) as executor:
                futures = {
                    executor.submit(
                        self._generate_page_image, project, page, style_context, deck_title
                    ): page["id"]
                    for page in pages
                }
                for future in as_completed(futures):
                    page_id = futures[future]
                    try:
                        payload = future.result()
                        ppt_store.update_page(
                            page_id,
                            generated_image_path=payload["generated_image_path"],
                            cached_image_path=payload["cached_image_path"],
                            is_dirty=False,
                            status="IMAGE_READY",
                        )
                        version_number = ppt_store.get_next_page_image_version(page_id)
                        ppt_store.create_page_image_version(
                            page_id=page_id,
                            version_number=version_number,
                            image_path=payload["generated_image_path"],
                            cached_image_path=payload["cached_image_path"],
                            prompt_used=payload["prompt_used"],
                            is_current=True,
                        )
                        image_completed += 1
                    except Exception as exc:
                        failed_count += 1
                        warnings.append(f"页面 {page_id} 图片生成失败: {exc}")
                        ppt_store.update_page(page_id, status="FAILED", is_dirty=True)
                    ppt_store.update_task(
                        task_id,
                        status="RUNNING",
                        progress=self._build_progress(
                            2,
                            3,
                            f"正在生成页面图片 {image_completed + failed_count}/{total_pages}",
                            warnings=warnings[-5:],
                            failed_count=failed_count,
                            page_ids=[page["id"] for page in pages],
                            phase="images",
                        ),
                    )

            ppt_store.update_project(project_id, status="COMPLETED")
            ppt_store.update_task(
                task_id,
                status="COMPLETED",
                progress=self._build_progress(
                    3,
                    3,
                    "完整 PPT 生成完成",
                    warnings=warnings[-5:],
                    failed_count=failed_count,
                    page_ids=[page["id"] for page in pages],
                    phase="completed",
                ),
                error_message=None,
            )
        except Exception as exc:
            ppt_store.update_task(
                task_id,
                status="FAILED",
                error_message=str(exc),
                progress=self._build_progress(
                    0,
                    3,
                    "完整 PPT 生成失败",
                    warnings=warnings[-5:],
                    failed_count=failed_count,
                    phase="failed",
                ),
            )

    def _run_page_chat_edit(
        self, task_id: str, project_id: str, page_id: str, edit_type: str
    ) -> None:
        warnings: list[str] = []
        try:
            project = ppt_store.get_project(project_id)
            if not project:
                raise ValueError("Project not found")
            project = asyncio.run(self._ensure_template_analysis(project))
            project, prep_warnings = asyncio.run(
                self._prepare_project_source_content(project_id, project)
            )
            warnings.extend(prep_warnings)
            page = ppt_store.get_page(page_id)
            if not page:
                raise ValueError("Page not found")

            total_steps = 1 if edit_type == "image_edit" else 2
            style_context = self._style_context_for_project(project)
            if edit_type != "image_edit":
                deck_pages = self._filter_pages(project_id, None)
                deck_outline_summary = self._build_deck_outline_summary(deck_pages)
                ppt_store.update_page(page_id, status="DESCRIPTION_QUEUED", is_dirty=True)
                ppt_store.update_task(
                    task_id,
                    status="RUNNING",
                    progress=self._build_progress(
                        0,
                        total_steps,
                        "正在根据对话重生成页面描述",
                        warnings=warnings[-5:],
                        failed_count=0,
                        page_ids=[page_id],
                        phase="descriptions",
                    ),
                )
                payload = self._generate_page_description(
                    project,
                    page,
                    "default",
                    deck_outline_summary,
                    style_context,
                )
                ppt_store.update_page(
                    page_id,
                    description_content=payload["description_content"],
                    image_prompt=payload["image_prompt"],
                    status="DESCRIPTION_READY",
                    is_dirty=True,
                )

            page = ppt_store.get_page(page_id)
            if not page:
                raise ValueError("Page not found")
            deck_pages = self._filter_pages(project_id, None)
            deck_title = self._resolve_project_title({"pages": deck_pages, **project})
            ppt_store.update_page(page_id, status="IMAGE_QUEUED", is_dirty=True)
            ppt_store.update_task(
                task_id,
                status="RUNNING",
                progress=self._build_progress(
                    total_steps - 1,
                    total_steps,
                    "正在根据对话重生成页面图片",
                    warnings=warnings[-5:],
                    failed_count=0,
                    page_ids=[page_id],
                    phase="images",
                ),
            )
            payload = self._generate_page_image(project, page, style_context, deck_title)
            ppt_store.update_page(
                page_id,
                generated_image_path=payload["generated_image_path"],
                cached_image_path=payload["cached_image_path"],
                is_dirty=False,
                status="IMAGE_READY",
            )
            version_number = ppt_store.get_next_page_image_version(page_id)
            ppt_store.create_page_image_version(
                page_id=page_id,
                version_number=version_number,
                image_path=payload["generated_image_path"],
                cached_image_path=payload["cached_image_path"],
                prompt_used=payload["prompt_used"],
                is_current=True,
            )
            ppt_store.update_task(
                task_id,
                status="COMPLETED",
                progress=self._build_progress(
                    total_steps,
                    total_steps,
                    "页面对话修改已完成",
                    warnings=warnings[-5:],
                    failed_count=0,
                    page_ids=[page_id],
                    phase="completed",
                ),
                error_message=None,
            )
        except Exception as exc:
            ppt_store.update_page(page_id, status="FAILED", is_dirty=True)
            ppt_store.update_task(
                task_id,
                status="FAILED",
                error_message=str(exc),
                progress=self._build_progress(
                    0,
                    1,
                    "页面对话修改失败",
                    warnings=warnings[-5:],
                    failed_count=1,
                    page_ids=[page_id],
                    phase="failed",
                ),
            )

    def _generate_page_image(
        self,
        project: dict[str, Any],
        page: dict[str, Any],
        style_context: StyleContext,
        deck_title: str,
    ) -> dict[str, Any]:
        ppt_store.update_page(page["id"], status="IMAGE_GENERATING")
        outline = page.get("outline_content") or {}
        title = outline.get("title") or "Untitled Slide"
        points = outline.get("points") or []
        description_text = (
            (page.get("description_content") or {}).get("text")
            if isinstance(page.get("description_content"), dict)
            else ""
        )
        prompt = (page.get("image_prompt") or "").strip() or self._fallback_image_prompt(
            title, points
        )
        layout = outline.get("layout") or self._default_layout(page["order_index"])
        data_url = asyncio.run(
            self.image_generator.generate_image(
                prompt=prompt,
                slide_title=title,
                slide_points=points,
                layout=layout,
                deck_title=deck_title,
                style_context=style_context,
                source_brief=project.get("normalized_content") or project.get("source_content") or "",
                reference_files=project.get("template_file_refs") or [],
                language=project.get("language") or "zh",
            )
        )
        if not data_url:
            raise ValueError("Image provider returned empty image")
        generated_path, cached_path = self._save_page_image(
            project["id"],
            page["id"],
            data_url,
            ppt_store.get_next_page_image_version(page["id"]),
        )
        return {
            "generated_image_path": generated_path,
            "cached_image_path": cached_path,
            "prompt_used": prompt,
            "description_text": description_text,
        }

    def _run_page_regeneration(
        self,
        task_id: str,
        project_id: str,
        page_id: str,
        regenerate_description: bool,
    ) -> None:
        warnings: list[str] = []
        try:
            project = ppt_store.get_project(project_id)
            if not project:
                raise ValueError("Project not found")
            project = asyncio.run(self._ensure_template_analysis(project))
            project, prep_warnings = asyncio.run(
                self._prepare_project_source_content(project_id, project)
            )
            warnings.extend(prep_warnings)

            page = ppt_store.get_page(page_id)
            if not page:
                raise ValueError("Page not found")

            total_steps = 2 if regenerate_description else 1
            style_context = self._style_context_for_project(project)

            if regenerate_description:
                deck_pages = self._filter_pages(project_id, None)
                deck_outline_summary = self._build_deck_outline_summary(deck_pages)
                ppt_store.update_page(page_id, status="DESCRIPTION_QUEUED", is_dirty=True)
                ppt_store.update_task(
                    task_id,
                    status="RUNNING",
                    progress=self._build_progress(
                        0,
                        total_steps,
                        "正在重生成页面描述",
                        warnings=warnings[-5:],
                        failed_count=0,
                        page_ids=[page_id],
                        phase="descriptions",
                    ),
                )
                payload = self._generate_page_description(
                    project,
                    page,
                    "default",
                    deck_outline_summary,
                    style_context,
                )
                ppt_store.update_page(
                    page_id,
                    description_content=payload["description_content"],
                    image_prompt=payload["image_prompt"],
                    status="DESCRIPTION_READY",
                    is_dirty=True,
                )

            page = ppt_store.get_page(page_id)
            if not page:
                raise ValueError("Page not found")
            deck_pages = self._filter_pages(project_id, None)
            deck_title = self._resolve_project_title({"pages": deck_pages, **project})
            ppt_store.update_page(page_id, status="IMAGE_QUEUED", is_dirty=True)
            ppt_store.update_task(
                task_id,
                status="RUNNING",
                progress=self._build_progress(
                    total_steps - 1,
                    total_steps,
                    "正在重生成页面图片",
                    warnings=warnings[-5:],
                    failed_count=0,
                    page_ids=[page_id],
                    phase="images",
                ),
            )
            payload = self._generate_page_image(project, page, style_context, deck_title)
            ppt_store.update_page(
                page_id,
                generated_image_path=payload["generated_image_path"],
                cached_image_path=payload["cached_image_path"],
                is_dirty=False,
                status="IMAGE_READY",
            )
            version_number = ppt_store.get_next_page_image_version(page_id)
            ppt_store.create_page_image_version(
                page_id=page_id,
                version_number=version_number,
                image_path=payload["generated_image_path"],
                cached_image_path=payload["cached_image_path"],
                prompt_used=payload["prompt_used"],
                is_current=True,
            )
            ppt_store.update_task(
                task_id,
                status="COMPLETED",
                progress=self._build_progress(
                    total_steps,
                    total_steps,
                    "页面重生成已完成",
                    warnings=warnings[-5:],
                    failed_count=0,
                    page_ids=[page_id],
                    phase="completed",
                ),
                error_message=None,
            )
        except Exception as exc:
            ppt_store.update_page(page_id, status="FAILED", is_dirty=True)
            ppt_store.update_task(
                task_id,
                status="FAILED",
                error_message=str(exc),
                progress=self._build_progress(
                    0,
                    1,
                    "页面重生成失败",
                    warnings=warnings[-5:],
                    failed_count=1,
                    page_ids=[page_id],
                    phase="failed",
                ),
            )

    def _save_page_image(
        self, project_id: str, page_id: str, data_url: str, version_number: int
    ) -> tuple[str, str]:
        header, b64_data = data_url.split(",", 1)
        image_bytes = base64.b64decode(b64_data)
        page_dir = (
            self.project_root
            / "data"
            / "user"
            / "ppt"
            / "projects"
            / project_id
            / "pages"
            / page_id
        )
        page_dir.mkdir(parents=True, exist_ok=True)
        png_path = page_dir / f"v{version_number}.png"
        jpg_path = page_dir / f"v{version_number}.jpg"
        png_path.write_bytes(image_bytes)

        image = Image.open(png_path)
        if image.mode != "RGB":
            image = image.convert("RGB")
        image.save(jpg_path, format="JPEG", quality=88)

        return self._to_output_relative(png_path), self._to_output_relative(jpg_path)

    def _collect_image_paths(self, pages: list[dict[str, Any]]) -> list[str]:
        paths = []
        for page in sorted(pages, key=lambda item: item["order_index"]):
            relative = page.get("generated_image_path") or page.get("cached_image_path")
            if not relative:
                continue
            absolute = self.project_root / "data" / "user" / relative
            if absolute.exists():
                paths.append(str(absolute))
        return paths

    def _filter_pages(self, project_id: str, page_ids: list[str] | None) -> list[dict[str, Any]]:
        pages = ppt_store.list_pages(project_id)
        if not page_ids:
            return pages
        selected_ids = set(page_ids)
        return [page for page in pages if page["id"] in selected_ids]

    def _project_to_presentation_outline(self, bundle: dict[str, Any]) -> dict[str, Any]:
        pages = sorted(bundle.get("pages") or [], key=lambda item: item["order_index"])
        style_context = self._style_context_for_project(bundle)
        return {
            "title": self._resolve_project_title(bundle),
            "subtitle": "",
            "themeColor": style_context.preset_color,
            "accentColor": "#f59e0b",
            "slides": [
                {
                    "title": (page.get("outline_content") or {}).get("title")
                    or f"Slide {index + 1}",
                    "points": (page.get("outline_content") or {}).get("points") or [],
                    "imagePrompt": page.get("image_prompt"),
                    "generatedImageUrl": self._to_output_url(
                        page.get("cached_image_path") or page.get("generated_image_path")
                    ),
                    "layout": (page.get("outline_content") or {}).get("layout")
                    or self._default_layout(index),
                    "pageId": page["id"],
                    "status": page.get("status"),
                    "isDirty": bool(page.get("is_dirty")),
                    "descriptionText": (page.get("description_content") or {}).get("text")
                    if isinstance(page.get("description_content"), dict)
                    else None,
                }
                for index, page in enumerate(pages)
            ],
        }

    async def _ensure_template_analysis(self, project: dict[str, Any]) -> dict[str, Any]:
        missing_fields = [
            field_name
            for field_name in (
                "reference_style_prompt",
                "reference_layout_prompt",
                "reference_content_prompt",
            )
            if not (project.get(field_name) or "").strip()
        ]
        if not missing_fields:
            return project
        if not project.get("template_image_path") and not (project.get("template_file_refs") or []):
            return project
        analysis = await self.template_analyzer.analyze(
            template_image_path=project.get("template_image_path"),
            template_file_refs=project.get("template_file_refs") or [],
        )
        update_fields: dict[str, Any] = {}
        if "reference_style_prompt" in missing_fields and analysis.reference_style_prompt:
            update_fields["reference_style_prompt"] = analysis.reference_style_prompt
        if "reference_layout_prompt" in missing_fields and analysis.reference_layout_prompt:
            update_fields["reference_layout_prompt"] = analysis.reference_layout_prompt
        if "reference_content_prompt" in missing_fields and analysis.reference_content_prompt:
            update_fields["reference_content_prompt"] = analysis.reference_content_prompt
        if not update_fields:
            return project
        updated = ppt_store.update_project(project["id"], **update_fields)
        return updated or {**project, **update_fields}

    def _resolve_project_title(self, bundle: dict[str, Any]) -> str:
        pages = bundle.get("pages") or []
        first_title = ""
        if pages:
            first_title = (pages[0].get("outline_content") or {}).get("title") or ""
        return first_title or self._resolve_project_topic(bundle) or "Presentation"

    def _resolve_project_topic(self, bundle: dict[str, Any]) -> str:
        for ref in bundle.get("source_refs") or bundle.get("reference_sources") or []:
            title = str(ref.get("title") or "").strip()
            if title:
                return title
        source_content = (
            bundle.get("source_content") or bundle.get("normalized_content") or ""
        ).strip()
        for line in source_content.splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                return stripped[2:].strip()
        return ""

    def _default_layout(self, index: int) -> str:
        return _LAYOUT_SEQUENCE[index % len(_LAYOUT_SEQUENCE)]

    def _build_style_context(
        self,
        *,
        style_preset_id: str | None = None,
        style_custom_text: str | None = None,
        reference_style_prompt: str | None = None,
        reference_layout_prompt: str | None = None,
        reference_content_prompt: str | None = None,
    ) -> StyleContext:
        return PptPromptManager.resolve_style_context(
            style_preset_id=style_preset_id,
            style_custom_text=style_custom_text,
            reference_style_prompt=reference_style_prompt,
            reference_layout_prompt=reference_layout_prompt,
            reference_content_prompt=reference_content_prompt,
        )

    def _style_context_for_project(self, project: dict[str, Any]) -> StyleContext:
        return self._build_style_context(
            style_preset_id=project.get("style_preset_id"),
            style_custom_text=project.get("style_custom_text"),
            reference_style_prompt=project.get("reference_style_prompt"),
            reference_layout_prompt=project.get("reference_layout_prompt"),
            reference_content_prompt=project.get("reference_content_prompt"),
        )

    async def _resolve_style_briefs_for_project(
        self,
        project: dict[str, Any],
    ) -> dict[str, str | None]:
        return await self._build_style_briefs(
            style_preset_id=project.get("style_preset_id"),
            style_custom_text=project.get("style_custom_text"),
            reference_style_prompt=project.get("reference_style_prompt"),
            reference_layout_prompt=project.get("reference_layout_prompt"),
            reference_content_prompt=project.get("reference_content_prompt"),
            language=project.get("language") or "zh",
        )

    async def _build_style_briefs(
        self,
        *,
        style_preset_id: str | None = None,
        style_custom_text: str | None = None,
        reference_style_prompt: str | None = None,
        reference_layout_prompt: str | None = None,
        reference_content_prompt: str | None = None,
        language: str = "zh",
    ) -> dict[str, str | None]:
        style_context = self._build_style_context(
            style_preset_id=style_preset_id,
            style_custom_text=style_custom_text,
            reference_style_prompt=reference_style_prompt,
            reference_layout_prompt=reference_layout_prompt,
            reference_content_prompt=reference_content_prompt,
        )
        fallback = style_context.style_summary(language)
        if not fallback:
            return {
                "outline_style_brief": None,
                "description_style_brief": None,
                "image_style_brief": None,
            }

        system_prompt, user_prompt = PptPromptManager.style_briefs(style_context, language)

        try:
            data = await self._complete_json_async(user_prompt, system_prompt)
        except Exception as exc:
            logger.warning(f"Falling back to raw style prompt for PPT style briefs: {exc}")
            return {
                "outline_style_brief": fallback,
                "description_style_brief": fallback,
                "image_style_brief": fallback,
            }

        outline_style_brief = (data.get("outline_style_brief") or "").strip() or fallback
        description_style_brief = (data.get("description_style_brief") or "").strip() or fallback
        image_style_brief = (data.get("image_style_brief") or "").strip() or fallback
        return {
            "outline_style_brief": outline_style_brief,
            "description_style_brief": description_style_brief,
            "image_style_brief": image_style_brief,
        }

    def _to_output_relative(self, path: Path) -> str:
        parts = path.parts
        user_idx = parts.index("user")
        return "/".join(parts[user_idx + 1 :])

    def _to_output_url(self, relative_path: str | None) -> str | None:
        if not relative_path:
            return None
        return f"/api/outputs/{relative_path}"

    def _resolve_relative_output_path(self, relative_path: str) -> Path:
        normalized = (relative_path or "").strip()
        if normalized.startswith("/api/outputs/"):
            normalized = normalized.replace("/api/outputs/", "", 1)
        return self.project_root / "data" / "user" / normalized

    def _bullet_join(self, points: list[str]) -> str:
        if not points:
            return "- no bullet points"
        return "\n".join(f"- {point}" for point in points)

    def _trim_text(self, value: str, max_chars: int) -> str:
        text = (value or "").strip()
        if len(text) <= max_chars:
            return text
        return text[:max_chars]

    def _fallback_image_prompt(self, title: str, points: list[str]) -> str:
        summary = ", ".join(points[:3])
        return f"{title}, {summary}, editorial presentation visual, 16:9 composition"

    def _build_deck_outline_summary(
        self, pages: list[dict[str, Any]], max_chars: int = 1800
    ) -> str:
        return self._trim_text(
            self.description_generator.build_deck_outline_summary(pages),
            max_chars,
        )

    def _build_slide_supporting_context(
        self,
        project: dict[str, Any],
        page: dict[str, Any],
        *,
        max_chars: int = 1200,
        max_chunks: int = 4,
    ) -> str:
        return self.description_generator.build_slide_supporting_context(
            project,
            page,
            max_chars=max_chars,
            max_chunks=max_chunks,
        )

    def _build_style_preview_theme(self, style_prompt: str) -> dict[str, Any]:
        colors = re.findall(r"#[0-9a-fA-F]{6}", style_prompt or "")
        background = self._parse_hex_color(colors[0]) if colors else (255, 255, 255)
        accent = self._parse_hex_color(colors[1]) if len(colors) > 1 else (79, 70, 229)
        lowered = (style_prompt or "").lower()
        if any(keyword in lowered for keyword in ["dark", "深色", "黑", "midnight"]):
            background = background or (17, 24, 39)
            title_color = (248, 250, 252)
            body_color = (226, 232, 240)
        else:
            background = background or (255, 255, 255)
            title_color = (17, 24, 39)
            body_color = (71, 85, 105)
        return {
            "background": background,
            "accent": accent or (79, 70, 229),
            "title_color": title_color,
            "body_color": body_color,
        }

    def _build_style_preview_svg(self, theme: dict[str, Any]) -> str:
        def rgb(key: str) -> str:
            value = theme.get(key, (0, 0, 0))
            return f"rgb({value[0]}, {value[1]}, {value[2]})"

        background = rgb("background")
        accent = rgb("accent")
        title = rgb("title_color")
        body = rgb("body_color")
        return f"""<svg width="640" height="360" viewBox="0 0 640 360" xmlns="http://www.w3.org/2000/svg">
  <rect width="640" height="360" rx="18" fill="{background}" />
  <rect width="640" height="28" fill="{accent}" />
  <text x="40" y="90" font-size="28" font-family="Arial" fill="{title}">Slide Title</text>
  <text x="40" y="140" font-size="16" font-family="Arial" fill="{body}">• Key insight goes here</text>
  <text x="40" y="170" font-size="16" font-family="Arial" fill="{body}">• Supporting detail goes here</text>
  <text x="40" y="200" font-size="16" font-family="Arial" fill="{body}">• Short takeaway goes here</text>
  <rect x="40" y="240" width="220" height="80" rx="12" fill="{accent}" opacity="0.12" />
  <rect x="280" y="240" width="320" height="80" rx="12" fill="{accent}" opacity="0.08" />
</svg>"""

    def _parse_hex_color(self, value: str | None) -> tuple[int, int, int] | None:
        text = (value or "").strip().lstrip("#")
        if len(text) == 3:
            text = "".join(char * 2 for char in text)
        if len(text) != 6:
            return None
        try:
            return tuple(int(text[index : index + 2], 16) for index in (0, 2, 4))
        except ValueError:
            return None

    def _build_progress(
        self,
        current: int,
        total: int,
        message: str,
        *,
        warnings: list[str] | None = None,
        failed_count: int,
        download_url: str | None = None,
        page_ids: list[str] | None = None,
        phase: str | None = None,
    ) -> dict[str, Any]:
        percentage = 100 if total <= 0 else int((current / total) * 100)
        return _TaskProgress(
            current=current,
            total=total,
            percentage=percentage,
            message=message,
            warnings=warnings or [],
            failed_count=failed_count,
            download_url=download_url,
            page_ids=page_ids or [],
            phase=phase,
        ).to_dict()

    def _list_active_tasks(self, project_id: str) -> list[dict[str, Any]]:
        return [
            task
            for task in ppt_store.list_tasks(project_id)
            if task.get("status") in _ACTIVE_TASK_STATUSES
        ]

    def _task_page_ids(self, task: dict[str, Any]) -> set[str]:
        progress = task.get("progress") or {}
        page_ids = progress.get("page_ids") or []
        return {str(page_id) for page_id in page_ids if page_id}

    def _assert_no_active_project_task(self, project_id: str) -> None:
        active_task = next(iter(self._list_active_tasks(project_id)), None)
        if active_task:
            raise ValueError("Another PPT generation task is already running for this project")

    def _assert_page_regeneration_allowed(self, project_id: str, page_id: str) -> None:
        for task in self._list_active_tasks(project_id):
            task_type = task.get("task_type")
            if task_type in _PROJECT_LEVEL_TASK_TYPES:
                raise ValueError(
                    "Project-level PPT generation is running; page regeneration is blocked"
                )
            if task_type in _PAGE_LEVEL_TASK_TYPES and page_id in self._task_page_ids(task):
                raise ValueError("This page already has an active regeneration task")

    def _assert_no_active_export_conflict(
        self, project_id: str, page_ids: list[str] | None = None
    ) -> None:
        target_page_ids = set(page_ids or [])
        for task in self._list_active_tasks(project_id):
            task_type = task.get("task_type")
            if task_type in _PROJECT_LEVEL_TASK_TYPES:
                raise ValueError(
                    "PPT generation is still running and export is temporarily blocked"
                )
            if task_type in _PAGE_LEVEL_TASK_TYPES:
                task_page_ids = self._task_page_ids(task)
                if not target_page_ids or not task_page_ids or task_page_ids & target_page_ids:
                    raise ValueError(
                        "Some slides are still regenerating and cannot be exported yet"
                    )

    def _classify_page_chat_edit(
        self, project: dict[str, Any], page: dict[str, Any], user_message: str
    ) -> str:
        return self.slide_editor.classify_edit(
            page,
            user_message,
            style_context=self._style_context_for_project(project),
        )

    def _rewrite_outline_from_chat(
        self, project: dict[str, Any], page: dict[str, Any], user_message: str
    ) -> dict[str, Any]:
        return self.slide_editor.rewrite_outline(
            page,
            user_message,
            style_context=self._style_context_for_project(project),
        )

    def _rewrite_description_from_chat(
        self, project: dict[str, Any], page: dict[str, Any], user_message: str
    ) -> dict[str, Any]:
        return self.slide_editor.rewrite_description(
            page,
            user_message,
            style_context=self._style_context_for_project(project),
        )

    def _rewrite_image_prompt_from_chat(
        self, project: dict[str, Any], page: dict[str, Any], user_message: str
    ) -> dict[str, Any]:
        return self.slide_editor.rewrite_image_prompt(
            page,
            user_message,
            style_context=self._style_context_for_project(project),
        )

    async def _complete_json_async(self, prompt: str, system_prompt: str) -> dict[str, Any]:
        llm_cfg = get_llm_config()
        kwargs = get_token_limit_kwargs(llm_cfg.model, 1200)
        try:
            raw = await llm_complete(
                prompt=prompt,
                system_prompt=system_prompt,
                model=llm_cfg.model,
                api_key=llm_cfg.api_key,
                base_url=llm_cfg.base_url,
                binding=llm_cfg.binding,
                temperature=0.3,
                response_format={"type": "json_object"},
                **kwargs,
            )
        except Exception as exc:
            if not self._should_retry_without_json_mode(exc):
                raise
            logger.warning(
                f"Model {llm_cfg.model} does not support response_format=json_object; "
                "retrying PPT JSON completion without JSON mode"
            )
            raw = await llm_complete(
                prompt=self._force_json_output(prompt),
                system_prompt=system_prompt,
                model=llm_cfg.model,
                api_key=llm_cfg.api_key,
                base_url=llm_cfg.base_url,
                binding=llm_cfg.binding,
                temperature=0.3,
                **kwargs,
            )
        data = self._extract_json(raw)
        if not data:
            raise ValueError("Failed to parse LLM JSON output")
        return data

    async def _complete_text_async(
        self,
        prompt: str,
        system_prompt: str,
        *,
        max_tokens: int = 3200,
        temperature: float = 0.3,
    ) -> str:
        llm_cfg = get_llm_config()
        kwargs = get_token_limit_kwargs(llm_cfg.model, max_tokens)
        raw = await llm_complete(
            prompt=prompt,
            system_prompt=system_prompt,
            model=llm_cfg.model,
            api_key=llm_cfg.api_key,
            base_url=llm_cfg.base_url,
            binding=llm_cfg.binding,
            temperature=temperature,
            **kwargs,
        )
        return (raw or "").strip()

    async def _normalize_to_deck_source_brief(
        self, project: dict[str, Any], source_content: str
    ) -> str:
        style_context = self._style_context_for_project(project)
        reference_context_xml = PptPromptManager._format_reference_context_xml(
            style_context=style_context,
            reference_files=project.get("source_refs") or project.get("reference_sources") or [],
            source_anchors=self._build_source_anchor_summary(project),
        )
        system_prompt, user_prompt = PptPromptManager.normalization_prompt(
            source_type=project.get("creation_type") or "from_sources",
            source_content=source_content,
            reference_context_xml=reference_context_xml,
        )
        raw = await self._complete_text_async(user_prompt, system_prompt, max_tokens=3600)
        if not raw:
            raise ValueError("Failed to generate DeckSourceBrief")
        return self._ensure_deck_source_brief_sections(
            raw,
            project.get("creation_type") or "from_sources",
        )

    def _ensure_deck_source_brief_sections(self, text: str, source_type: str) -> str:
        normalized = (text or "").strip()
        required_sections = [
            "## Core Theme",
            "## Key Findings",
            "## Supporting Evidence",
            "## Source Anchors",
        ]
        optional_for_sources = [
            "## Consensus",
            "## Divergence",
            "## Complementary Evidence",
        ]
        for section in required_sections:
            if section.lower() not in normalized.lower():
                normalized = f"{normalized}\n\n{section}\n- None".strip()
        if (source_type or "").strip().lower() == "from_sources":
            for section in optional_for_sources:
                if section.lower() not in normalized.lower():
                    continue
        return normalized.strip()

    def _build_source_anchor_summary(self, project: dict[str, Any]) -> str:
        anchors: list[str] = []
        for ref in project.get("source_refs") or project.get("reference_sources") or []:
            title = str(ref.get("title") or "Untitled source").strip()
            source_key = str(ref.get("source_key") or "").strip()
            ref_type = str(ref.get("type") or "source").strip()
            anchor = f"- {title} [{ref_type}]"
            if source_key:
                anchor += f" ({source_key})"
            anchors.append(anchor)
        return "\n".join(anchors)

    def _complete_json_sync(self, prompt: str, system_prompt: str) -> dict[str, Any]:
        return asyncio.run(self._complete_json_async(prompt, system_prompt))

    def _guess_image_content_type(self, image_path: Path) -> str:
        suffix = image_path.suffix.lower()
        if suffix == ".png":
            return "image/png"
        if suffix == ".webp":
            return "image/webp"
        return "image/jpeg"

    def _extract_json(self, text: str) -> dict[str, Any] | None:
        try:
            data = json.loads(text)
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            pass
        match = re.search(r"```json\s*([\s\S]*?)\s*```", text, flags=re.IGNORECASE)
        if match:
            try:
                data = json.loads(match.group(1).strip())
                return data if isinstance(data, dict) else None
            except Exception:
                return None
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(text[start : end + 1])
                return data if isinstance(data, dict) else None
            except Exception:
                return None
        return None

    def _force_json_output(self, prompt: str) -> str:
        return (
            f"{prompt.rstrip()}\n\n"
            "IMPORTANT: Return a single valid JSON object only. "
            "Do not use markdown fences. Do not add explanations before or after the JSON."
        )

    def _should_retry_without_json_mode(self, exc: Exception) -> bool:
        message = str(exc).lower()
        if "json_object" not in message:
            return False
        return any(
            marker in message
            for marker in ("not supported", "not valid", "invalidparameter", "unsupported")
        )


_service: PptProjectService | None = None


def get_ppt_project_service(project_root: Path | None = None) -> PptProjectService:
    global _service
    if _service is None:
        if project_root is None:
            project_root = Path(__file__).resolve().parents[3]
        _service = PptProjectService(project_root)
    return _service
