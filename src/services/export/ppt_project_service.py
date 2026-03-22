from __future__ import annotations

import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
import io
import json
from pathlib import Path
import re
from typing import Any
import uuid

from PIL import Image

from src.api.utils.notebook_manager import NotebookManager
from src.logging import get_logger
from src.services.config import get_banana_ppt_config, load_config_with_main
from src.services.export.banana_ppt_service import BananaPptService
from src.services.export.ppt_generator import PPTGenerator
from src.services.export.ppt_image_export_service import PptImageExportService
from src.services.export.source_report import SourceReportGenerator
from src.services.export.ppt_task_manager import ppt_task_manager
from src.services.llm import complete as llm_complete
from src.services.llm import get_llm_client, get_llm_config, get_token_limit_kwargs
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
    "idea",
    "outline",
    "descriptions",
    "from_research",
    "from_notebook",
    "from_sources",
}
_NOTEBOOK_RECORD_CHAR_LIMIT = 2400
_NOTEBOOK_TOTAL_CHAR_LIMIT = 14000


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
        self.banana_service = BananaPptService(project_root)
        self.export_service = PptImageExportService(project_root)
        task_cfg = self.ppt_v2_config.get("task", {}) or {}
        self.description_workers = int(task_cfg.get("description_workers", 4))
        self.image_workers = int(task_cfg.get("image_workers", 3))
        self.polling_hint_ms = int(task_cfg.get("polling_hint_ms", 1500))

    def get_config(self) -> dict[str, Any]:
        ppt_cfg = self.config.get("export", {}).get("ppt", {}) or {}
        style_templates = self.banana_config.style_templates or ppt_cfg.get("style_templates", [])
        return {
            "enabled": self.ppt_v2_config.get("enabled", True),
            "max_slides": int(
                self.ppt_v2_config.get(
                    "max_slides", self.banana_config.max_slides or ppt_cfg.get("max_slides", 15)
                )
            ),
            "style_templates": style_templates,
            "polling_hint_ms": self.polling_hint_ms,
            "creation_modes": [
                "auto",
                "idea",
                "outline",
                "descriptions",
                "from_research",
                "from_notebook",
                "from_sources",
            ],
        }

    def create_project(
        self,
        *,
        notebook_id: str | None,
        session_id: str | None,
        creation_type: str,
        idea_prompt: str | None,
        outline_text: str | None,
        description_text: str | None,
        source_content: str | None,
        template_style: str | None,
        template_image_path: str | None,
        reference_style_prompt: str | None,
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
            frozen_source_content, frozen_source_refs = self._freeze_research_project_input(
                notebook_id=notebook_id,
                session_id=session_id,
                source_content=frozen_source_content,
                source_refs=frozen_source_refs,
            )
        elif creation_type == "from_notebook":
            frozen_source_content = frozen_source_content or self._freeze_notebook_project_input(
                notebook_id=notebook_id,
                record_ids=record_ids or [],
            )
        elif creation_type == "from_sources":
            if not frozen_source_refs:
                raise ValueError("source_refs are required for from_sources")

        project = ppt_store.create_project(
            notebook_id=notebook_id,
            session_id=session_id,
            creation_type=creation_type,
            idea_prompt=(idea_prompt or "").strip() or None,
            outline_text=(outline_text or "").strip() or None,
            description_text=(description_text or "").strip() or None,
            source_content=frozen_source_content,
            template_style=(template_style or "").strip() or None,
            template_image_path=(template_image_path or "").strip() or None,
            reference_style_prompt=(reference_style_prompt or "").strip() or None,
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
            derived_style_prompt = await self._derive_reference_style_prompt(output_path)
        except Exception as exc:
            output_path.unlink(missing_ok=True)
            raise ReferenceStyleExtractionError(str(exc)) from exc

        relative_path = self._to_output_relative(output_path)
        return {
            "image_path": relative_path,
            "image_url": self._to_output_url(relative_path),
            "image_name": safe_name,
            "derived_style_prompt": derived_style_prompt,
            "content_type": content_type or self._guess_image_content_type(output_path),
        }

    async def preview_style(self, style_prompt: str | None = None) -> dict[str, Any]:
        generator = PPTGenerator(
            export_dir=self.project_root / "data" / "user" / "research" / "exports"
        )
        theme = generator._parse_theme({})
        normalized_prompt = (style_prompt or "").strip()
        if normalized_prompt:
            try:
                sample_markdown = "# Preview Title\n\n## Section\n- Point one\n- Point two"
                spec = await generator._generate_ppt_spec(
                    sample_markdown, normalized_prompt, max_slides=5
                )
                theme = (
                    generator._parse_theme(spec.get("theme", {}))
                    if spec
                    else generator._parse_theme({})
                )
            except Exception:
                theme = generator._parse_theme({})
        return {
            "theme": theme,
            "preview_svg": self._build_style_preview_svg(theme),
        }

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
        image_data_url = await self.banana_service.generate_image(
            prompt=prompt,
            slide_title=slide_title,
            slide_points=slide_points,
            layout=layout,
            deck_title=deck_title,
            style_prompt=style_prompt,
        )
        return {"image_data_url": image_data_url}

    async def derive_idea(self, source_content: str) -> dict[str, Any]:
        text = (source_content or "").strip()
        if not text:
            raise ValueError("source_content is empty")
        system_prompt = (
            "You turn long source material into a single concise PPT generation idea. "
            "Return ONLY valid JSON with key idea_prompt."
        )
        user_prompt = (
            "Summarize the following material into one presentation brief. "
            "Keep it under 60 Chinese characters or 20 English words.\n\n"
            f"Source:\n{self._trim_text(text, 6000)}"
        )
        data = await self._complete_json_async(user_prompt, system_prompt)
        return {"idea_prompt": (data.get("idea_prompt") or "").strip()}

    async def derive_outline(
        self, source_content: str, *, style_prompt: str | None = None, max_slides: int | None = None
    ) -> dict[str, Any]:
        style_briefs = await self._build_style_briefs(template_style=style_prompt)
        outline = await self.banana_service.generate_outline(
            source_content=source_content,
            style_prompt=style_briefs.get("outline_style_brief"),
            max_slides=max_slides,
        )
        return {
            "outline_text": self._outline_to_markdown(outline),
            "presentation_outline": outline,
        }

    async def generate_outline(
        self,
        project_id: str,
        *,
        style_prompt: str | None = None,
        max_slides: int | None = None,
    ) -> dict[str, Any]:
        project = ppt_store.get_project(project_id)
        if not project:
            raise ValueError("Project not found")
        if style_prompt is not None:
            project = (
                ppt_store.update_project(
                    project_id,
                    template_style=(style_prompt or "").strip() or None,
                )
                or project
            )
        project = await self._ensure_reference_style_prompt(project)
        project, _ = await self._prepare_project_source_content(project_id, project)

        normalized_outline = await self._build_outline(
            project, style_prompt=style_prompt, max_slides=max_slides
        )
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
        style_prompt: str | None = None,
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
            style_prompt,
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
            updated_outline = self._rewrite_outline_from_chat(page, user_message)
            assistant_message = updated_outline.pop("assistant_message")
            page = self.update_page(
                project_id,
                page_id,
                title=updated_outline["title"],
                points=updated_outline["points"],
            )
        elif edit_type == "description_edit":
            updated_description = self._rewrite_description_from_chat(page, user_message)
            assistant_message = updated_description.pop("assistant_message")
            page = self.update_page(
                project_id,
                page_id,
                description_text=updated_description["description_text"],
            )
        else:
            updated_image = self._rewrite_image_prompt_from_chat(page, user_message)
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
        ppt_task_manager.submit(task["id"], self._run_page_chat_edit, project_id, page_id, edit_type)
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
        if (
            title is None
            and points is None
            and description_text is None
            and image_prompt is None
        ):
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
        style_prompt: str | None,
        max_slides: int | None,
    ) -> dict[str, Any]:
        limit = int(max_slides or self.get_config()["max_slides"])

        if project["creation_type"] == "outline":
            slides = self._parse_outline_text(project.get("outline_text") or "", limit)
            return {
                "title": self._extract_outline_title(project.get("outline_text") or ""),
                "subtitle": "",
                "themeColor": "#3b82f6",
                "accentColor": "#f59e0b",
                "slides": slides,
            }

        style_briefs = await self._resolve_style_briefs_for_project(
            project, style_prompt=style_prompt
        )
        if project["creation_type"] == "descriptions":
            source_content = (
                project.get("description_text")
                or project.get("source_content")
                or project.get("idea_prompt")
                or ""
            )
        elif project["creation_type"] in {"from_research", "from_notebook", "from_sources"}:
            source_content = (
                project.get("source_content")
                or project.get("normalized_content")
                or project.get("idea_prompt")
                or project.get("description_text")
                or ""
            )
        else:
            source_content = (
                project.get("idea_prompt")
                or project.get("source_content")
                or project.get("description_text")
                or ""
            )
        outline = await self.banana_service.generate_outline(
            source_content=source_content,
            style_prompt=style_briefs.get("outline_style_brief"),
            max_slides=limit,
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

        if creation_type == "from_research":
            if project.get("source_content") and project.get("source_refs"):
                return project, []
            source_content, source_refs = self._freeze_research_project_input(
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
            return project, []

        if creation_type == "from_notebook":
            if project.get("source_content"):
                return project, []
            source_content = self._freeze_notebook_project_input(
                notebook_id=project.get("notebook_id"),
                record_ids=project.get("record_ids") or [],
            )
            project = ppt_store.update_project(project_id, source_content=source_content) or project
            return project, []

        if project.get("normalized_content"):
            if not project.get("source_content"):
                project = (
                    ppt_store.update_project(project_id, source_content=project.get("normalized_content"))
                    or project
                )
            return project, []

        source_refs = project.get("source_refs") or project.get("reference_sources") or []
        if not source_refs:
            raise ValueError("from_sources requires frozen source_refs")
        generator = SourceReportGenerator()
        result = await generator.generate(
            sources=[dict(item) for item in source_refs],
            topic=(project.get("idea_prompt") or "").strip() or None,
        )
        markdown = (result.get("markdown") or "").strip()
        if not markdown:
            raise ValueError("No synthesized markdown was produced from selected sources")
        warnings = self._format_skipped_source_warnings(result.get("skipped_sources") or [])
        project = (
            ppt_store.update_project(
                project_id,
                source_content=markdown,
                normalized_content=markdown,
                content_cached_at=datetime.now(timezone.utc),
            )
            or project
        )
        return project, warnings

    def _freeze_research_project_input(
        self,
        *,
        notebook_id: str | None,
        session_id: str | None,
        source_content: str | None,
        source_refs: list[dict[str, Any]],
    ) -> tuple[str, list[dict[str, Any]]]:
        frozen_content = (source_content or "").strip()
        frozen_refs = [dict(item) for item in source_refs]
        if frozen_content and frozen_refs:
            return frozen_content, frozen_refs
        session = self._resolve_notebook_session(notebook_id, session_id)
        research_report = (session.get("research_report") or "").strip() or frozen_content
        if not research_report:
            raise ValueError("No research report available for from_research")
        if not frozen_refs:
            frozen_refs = [
                {
                    "type": "report",
                    "title": session.get("title") or "Research Report",
                    "source_key": session.get("session_id") or session_id,
                    "content": research_report,
                }
            ]
        return research_report, frozen_refs

    def _freeze_notebook_project_input(
        self,
        *,
        notebook_id: str | None,
        record_ids: list[str],
    ) -> str:
        if not notebook_id:
            raise ValueError("notebook_id is required for from_notebook")
        notebook = NotebookManager().get_notebook(notebook_id)
        if not notebook:
            raise ValueError("Notebook not found")
        records = notebook.get("records") or []
        if record_ids:
            wanted = {record_id for record_id in record_ids if record_id}
            records = [record for record in records if record.get("id") in wanted]
        if not records:
            raise ValueError("No notebook records available for from_notebook")
        return self._normalize_notebook_records(records)

    def _resolve_notebook_session(
        self, notebook_id: str | None, session_id: str | None
    ) -> dict[str, Any]:
        if not notebook_id:
            raise ValueError("notebook_id is required for from_research")
        manager = NotebookManager()
        if session_id:
            session = next(
                (
                    item
                    for item in manager.list_sessions(notebook_id)
                    if item.get("session_id") == session_id
                ),
                None,
            )
            if session:
                return session
        session = manager.get_latest_session(notebook_id)
        if not session:
            raise ValueError("Notebook session not found")
        return session

    def _normalize_notebook_records(self, records: list[dict[str, Any]]) -> str:
        ordered = sorted(records, key=lambda item: item.get("created_at", 0))
        blocks: list[str] = []
        total_chars = 0
        for index, record in enumerate(ordered, start=1):
            title = (record.get("title") or f"Record {index}").strip()
            record_type = (record.get("type") or "note").strip()
            user_query = (record.get("user_query") or "").strip()
            output = self._trim_text(record.get("output") or "", _NOTEBOOK_RECORD_CHAR_LIMIT)
            if not output:
                continue
            block_lines = [f"## {index}. {title}", f"Type: {record_type}"]
            if user_query:
                block_lines.append(f"User Query: {user_query}")
            block_lines.extend(["Content:", output])
            block = "\n".join(block_lines).strip()
            next_total = total_chars + len(block) + (2 if blocks else 0)
            if blocks and next_total > _NOTEBOOK_TOTAL_CHAR_LIMIT:
                break
            blocks.append(block)
            total_chars = next_total
            if total_chars >= _NOTEBOOK_TOTAL_CHAR_LIMIT:
                break
        if not blocks:
            raise ValueError("Notebook records do not contain usable content")
        return "\n\n".join(blocks)

    def _format_skipped_source_warnings(self, skipped_sources: list[dict[str, Any]]) -> list[str]:
        warnings: list[str] = []
        for source in skipped_sources:
            title = (source.get("title") or "Untitled source").strip()
            reason = (source.get("reason") or "skipped").strip()
            warnings.append(f"Skipped source: {title} ({reason})")
        return warnings

    def _smart_merge_pages(
        self, project_id: str, existing_pages: list[dict[str, Any]], slides: list[dict[str, Any]]
    ) -> None:
        used_ids: set[str] = set()
        survivors: set[str] = set()
        for index, slide in enumerate(slides):
            matched = self._match_page(existing_pages, slide, index, used_ids)
            fields = {
                "order_index": index,
                "part": slide.get("part"),
                "outline_content": {
                    "title": slide.get("title") or f"Slide {index + 1}",
                    "points": slide.get("points") or [],
                    "layout": slide.get("layout") or self._default_layout(index),
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

    def _match_page(
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
            if not old_title or not new_title:
                continue
            ratio = SequenceMatcher(None, old_title, new_title).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = page
        if best_match and best_ratio >= 0.82:
            return best_match

        return next(
            (
                page
                for page in existing_pages
                if page["id"] not in used_ids and page["order_index"] == order_index
            ),
            None,
        )

    def _run_generate_descriptions(
        self, task_id: str, project_id: str, page_ids: list[str], detail_level: str
    ) -> None:
        project = ppt_store.get_project(project_id)
        if not project:
            ppt_store.update_task(task_id, status="FAILED", error_message="Project not found")
            return
        project = asyncio.run(self._ensure_reference_style_prompt(project))
        pages = self._filter_pages(project_id, page_ids or None)
        deck_pages = self._filter_pages(project_id, None)
        deck_outline_summary = self._build_deck_outline_summary(deck_pages)
        style_briefs = asyncio.run(self._resolve_style_briefs_for_project(project))
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
                    style_briefs,
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
        style_briefs: dict[str, str | None],
    ) -> dict[str, Any]:
        ppt_store.update_page(page["id"], status="DESCRIPTION_GENERATING")
        outline = page.get("outline_content") or {}
        title = outline.get("title") or "Untitled Slide"
        points = outline.get("points") or []
        language = project.get("language") or "zh"
        supporting_report_snippets = self._build_slide_supporting_context(project, page)
        system_prompt = (
            "You expand a confirmed PPT outline into production-ready slide briefs. "
            "Return ONLY valid JSON with keys text and image_prompt.\n\n"
            "Rules:\n"
            "- Follow the current slide only; do not redesign the deck.\n"
            "- Use supporting evidence to enrich the slide, not replace its structure.\n"
            "- Keep the language concise, presentation-ready, and specific.\n"
            "- image_prompt must align with the slide message and visual brief."
        )
        user_prompt = (
            f"Deck outline summary:\n{deck_outline_summary or 'No deck outline summary available.'}\n\n"
            f"Current slide:\n- Title: {title}\n- Points:\n{self._bullet_join(points)}\n\n"
            f"Supporting report snippets:\n{supporting_report_snippets or 'No supporting evidence available.'}\n\n"
            f"Visual brief:\n{style_briefs.get('description_style_brief') or 'default'}\n\n"
            "Requirements:\n"
            "- Write one polished per-slide description.\n"
            "- Make it vivid, precise, and easy to turn into a visual slide.\n"
            "- Keep it faithful to the current slide's meaning.\n"
            "- Avoid repeating bullet points verbatim.\n"
            "- image_prompt should describe one 16:9 professional business/editorial visual concept.\n"
            "- Avoid logos, readable text, screenshots, fantasy, and decorative-only visuals.\n"
            f"- Language: {language}\n"
            f"- Detail level: {detail_level}\n\n"
            "Return JSON only."
        )
        data = self._complete_json_sync(user_prompt, system_prompt)
        text = (data.get("text") or "").strip()
        image_prompt = (data.get("image_prompt") or "").strip()
        if not text:
            raise ValueError("Description response missing text")
        return {
            "description_content": {
                "text": text,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "detail_level": detail_level,
            },
            "image_prompt": image_prompt or self._fallback_image_prompt(title, points),
        }

    def _run_generate_images(self, task_id: str, project_id: str, page_ids: list[str]) -> None:
        project = ppt_store.get_project(project_id)
        if not project:
            ppt_store.update_task(task_id, status="FAILED", error_message="Project not found")
            return
        project = asyncio.run(self._ensure_reference_style_prompt(project))
        pages = self._filter_pages(project_id, page_ids or None)
        deck_pages = self._filter_pages(project_id, None)
        deck_title = self._resolve_project_title({"pages": deck_pages, **project})
        style_briefs = asyncio.run(self._resolve_style_briefs_for_project(project))
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
                executor.submit(
                    self._generate_page_image, project, page, style_briefs, deck_title
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
        style_prompt: str | None,
        max_slides: int | None,
        detail_level: str,
    ) -> None:
        warnings: list[str] = []
        failed_count = 0
        try:
            project = ppt_store.get_project(project_id)
            if not project:
                raise ValueError("Project not found")
            if style_prompt is not None:
                project = (
                    ppt_store.update_project(
                        project_id,
                        template_style=(style_prompt or "").strip() or None,
                    )
                    or project
                )

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
            project, prep_warnings = asyncio.run(self._prepare_project_source_content(project_id, project))
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
            asyncio.run(self.generate_outline(project_id, style_prompt=style_prompt, max_slides=max_slides))

            project = ppt_store.get_project(project_id) or project
            project = asyncio.run(self._ensure_reference_style_prompt(project))
            pages = self._filter_pages(project_id, None)
            if not pages:
                raise ValueError("No pages available after outline generation")
            deck_pages = self._filter_pages(project_id, None)
            deck_outline_summary = self._build_deck_outline_summary(deck_pages)
            style_briefs = asyncio.run(self._resolve_style_briefs_for_project(project))

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
                        style_briefs,
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
                        self._generate_page_image, project, page, style_briefs, deck_title
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
            project = asyncio.run(self._ensure_reference_style_prompt(project))
            project, prep_warnings = asyncio.run(self._prepare_project_source_content(project_id, project))
            warnings.extend(prep_warnings)
            page = ppt_store.get_page(page_id)
            if not page:
                raise ValueError("Page not found")

            total_steps = 1 if edit_type == "image_edit" else 2
            style_briefs = asyncio.run(self._resolve_style_briefs_for_project(project))
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
                    style_briefs,
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
            payload = self._generate_page_image(project, page, style_briefs, deck_title)
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
        style_briefs: dict[str, str | None],
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
            self.banana_service.generate_image(
                prompt=prompt,
                slide_title=title,
                slide_points=points,
                layout=layout,
                deck_title=deck_title,
                style_prompt=style_briefs.get("image_style_brief"),
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
            project = asyncio.run(self._ensure_reference_style_prompt(project))
            project, prep_warnings = asyncio.run(
                self._prepare_project_source_content(project_id, project)
            )
            warnings.extend(prep_warnings)

            page = ppt_store.get_page(page_id)
            if not page:
                raise ValueError("Page not found")

            total_steps = 2 if regenerate_description else 1
            style_briefs = asyncio.run(self._resolve_style_briefs_for_project(project))

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
                    style_briefs,
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
            payload = self._generate_page_image(project, page, style_briefs, deck_title)
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
        return {
            "title": self._resolve_project_title(bundle),
            "subtitle": "",
            "themeColor": "#3b82f6",
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

    async def _ensure_reference_style_prompt(self, project: dict[str, Any]) -> dict[str, Any]:
        if not project.get("template_image_path") or project.get("reference_style_prompt"):
            return project
        image_path = self._resolve_relative_output_path(project["template_image_path"])
        if not image_path.exists():
            raise ReferenceStyleExtractionError("Reference image file not found")
        derived_style_prompt = await self._derive_reference_style_prompt(image_path)
        updated = ppt_store.update_project(
            project["id"],
            reference_style_prompt=derived_style_prompt,
        )
        return updated or {**project, "reference_style_prompt": derived_style_prompt}

    def _resolve_project_title(self, bundle: dict[str, Any]) -> str:
        pages = bundle.get("pages") or []
        first_title = ""
        if pages:
            first_title = (pages[0].get("outline_content") or {}).get("title") or ""
        return (
            first_title
            or bundle.get("idea_prompt")
            or self._extract_outline_title(bundle.get("outline_text") or "")
            or "Presentation"
        )

    def _extract_outline_title(self, outline_text: str) -> str:
        for line in outline_text.splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                return stripped[2:].strip()
        return "Presentation"

    def _parse_outline_text(self, outline_text: str, max_slides: int) -> list[dict[str, Any]]:
        slides: list[dict[str, Any]] = []
        current_part: str | None = None
        current_slide: dict[str, Any] | None = None

        def flush() -> None:
            nonlocal current_slide
            if current_slide:
                slides.append(current_slide)
            current_slide = None

        for raw_line in (outline_text or "").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("# ") and slides:
                current_part = line[2:].strip()
                continue
            if line.startswith("# ") and not slides and current_slide is None:
                current_part = line[2:].strip()
                continue
            if line.startswith("## "):
                flush()
                current_slide = {
                    "title": line[3:].strip(),
                    "points": [],
                    "part": current_part,
                    "layout": self._default_layout(len(slides)),
                }
                continue
            numbered = re.match(r"^\d+[.)]\s+(.*)$", line)
            if numbered:
                flush()
                current_slide = {
                    "title": numbered.group(1).strip(),
                    "points": [],
                    "part": current_part,
                    "layout": self._default_layout(len(slides)),
                }
                continue
            bullet = re.match(r"^[-*+]\s+(.*)$", line)
            if bullet and current_slide is not None:
                current_slide["points"].append(bullet.group(1).strip())
                continue
            if current_slide is None:
                current_slide = {
                    "title": line,
                    "points": [],
                    "part": current_part,
                    "layout": self._default_layout(len(slides)),
                }
            else:
                current_slide["points"].append(line)

        flush()
        if not slides:
            slides = [
                {
                    "title": "Overview",
                    "points": ["Summarize the topic"],
                    "layout": self._default_layout(0),
                    "part": None,
                }
            ]
        return slides[: max(1, max_slides)]

    def _outline_to_markdown(self, outline: dict[str, Any]) -> str:
        lines = [f"# {outline.get('title') or 'Presentation'}", ""]
        for slide in outline.get("slides") or []:
            lines.append(f"## {slide.get('title') or 'Slide'}")
            for point in slide.get("points") or []:
                lines.append(f"- {point}")
            lines.append("")
        return "\n".join(lines).strip()

    def _default_layout(self, index: int) -> str:
        return _LAYOUT_SEQUENCE[index % len(_LAYOUT_SEQUENCE)]

    async def _resolve_style_briefs_for_project(
        self,
        project: dict[str, Any],
        *,
        style_prompt: str | None = None,
    ) -> dict[str, str | None]:
        template_style = style_prompt if style_prompt is not None else project.get("template_style")
        return await self._build_style_briefs(
            template_style=template_style,
            reference_style_prompt=project.get("reference_style_prompt"),
        )

    async def _build_style_briefs(
        self,
        *,
        template_style: str | None = None,
        reference_style_prompt: str | None = None,
    ) -> dict[str, str | None]:
        sections = self._split_template_style_sections(template_style)
        fallback = self._compose_effective_style_prompt_from_parts(
            sections.get("preset"),
            reference_style_prompt,
            sections.get("user"),
        )
        if not fallback:
            return {
                "outline_style_brief": None,
                "description_style_brief": None,
                "image_style_brief": None,
            }

        system_prompt = (
            "You are a presentation style planner. "
            "Return ONLY valid JSON with keys outline_style_brief, "
            "description_style_brief, image_style_brief.\n\n"
            "Rules:\n"
            "- outline_style_brief should include only planning-level guidance: tone, density, palette tendency, layout rhythm.\n"
            "- description_style_brief can additionally include image treatment, negative space, and typography mood.\n"
            "- image_style_brief can be the most specific and visually rich.\n"
            "- Keep all briefs concise, production-ready, and non-redundant.\n"
            "- User override has the highest priority.\n"
            "- Do not invent a brand identity that is not implied by the inputs."
        )
        user_prompt = (
            f"Preset base:\n{sections.get('preset') or 'None'}\n\n"
            f"Reference-image summary:\n{(reference_style_prompt or '').strip() or 'None'}\n\n"
            f"User override:\n{sections.get('user') or 'None'}\n\n"
            "Return concise briefs for PPT outline, slide description, and image generation."
        )

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

    def _split_template_style_sections(self, template_style: str | None) -> dict[str, str]:
        text = (template_style or "").strip()
        if not text:
            return {"preset": "", "user": ""}

        preset_lines: list[str] = []
        user_lines: list[str] = []
        default_lines: list[str] = []
        current = "default"
        for raw_line in text.splitlines():
            line = raw_line.rstrip()
            lowered = line.strip().lower()
            if lowered == "preset base:" or lowered == "source-derived guidance:":
                current = "preset"
                continue
            if lowered == "user override:":
                current = "user"
                continue
            if current == "preset":
                preset_lines.append(line)
            elif current == "user":
                user_lines.append(line)
            else:
                default_lines.append(line)

        if not preset_lines and not user_lines:
            preset_lines = default_lines
        elif default_lines:
            preset_lines = [*preset_lines, *default_lines]

        return {
            "preset": "\n".join(line for line in preset_lines if line.strip()).strip(),
            "user": "\n".join(line for line in user_lines if line.strip()).strip(),
        }

    def _compose_effective_style_prompt(
        self,
        project: dict[str, Any],
        *,
        style_prompt: str | None = None,
    ) -> str | None:
        return self._compose_effective_style_prompt_from_parts(
            project.get("reference_style_prompt"),
            style_prompt if style_prompt is not None else project.get("template_style"),
        )

    def _compose_effective_style_prompt_from_parts(self, *parts: str | None) -> str | None:
        normalized = [str(part).strip() for part in parts if str(part or "").strip()]
        return "\n\n".join(normalized) if normalized else None

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
        lines: list[str] = []
        for index, page in enumerate(sorted(pages, key=lambda item: item["order_index"])):
            outline = page.get("outline_content") or {}
            title = (outline.get("title") or f"Slide {index + 1}").strip()
            points = outline.get("points") or []
            lines.append(f"Slide {index + 1}: {title}")
            for point in points[:4]:
                lines.append(f"- {point}")
            lines.append("")
        return self._trim_text("\n".join(lines).strip(), max_chars)

    def _build_slide_supporting_context(
        self,
        project: dict[str, Any],
        page: dict[str, Any],
        *,
        max_chars: int = 1200,
        max_chunks: int = 4,
    ) -> str:
        source_text = (
            project.get("source_content")
            or project.get("description_text")
            or project.get("idea_prompt")
            or project.get("outline_text")
            or ""
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
                raise ValueError("PPT generation is still running and export is temporarily blocked")
            if task_type in _PAGE_LEVEL_TASK_TYPES:
                task_page_ids = self._task_page_ids(task)
                if not target_page_ids or not task_page_ids or task_page_ids & target_page_ids:
                    raise ValueError(
                        "Some slides are still regenerating and cannot be exported yet"
                    )

    def _classify_page_chat_edit(
        self, project: dict[str, Any], page: dict[str, Any], user_message: str
    ) -> str:
        lowered = user_message.lower()
        image_keywords = ["图片", "配图", "图像", "视觉", "插画", "照片", "背景", "image", "visual"]
        outline_keywords = ["标题", "要点", "结构", "顺序", "大纲", "分成", "合并", "outline"]
        description_keywords = ["描述", "文案", "内容", "表述", "展开", "精简", "润色", "description"]
        if any(keyword in lowered for keyword in image_keywords):
            return "image_edit"
        if any(keyword in lowered for keyword in outline_keywords):
            return "outline_edit"
        if any(keyword in lowered for keyword in description_keywords):
            return "description_edit"

        outline = page.get("outline_content") or {}
        system_prompt = (
            "You classify a slide editing request. "
            "Return ONLY valid JSON with key edit_type.\n\n"
            "Allowed values: outline_edit, description_edit, image_edit."
        )
        user_prompt = (
            f"Slide title: {outline.get('title') or 'Untitled'}\n"
            f"Slide points:\n{self._bullet_join(outline.get('points') or [])}\n\n"
            f"User request:\n{user_message}\n\n"
            "Classify which part of the slide the user mainly wants to change."
        )
        data = self._complete_json_sync(user_prompt, system_prompt)
        edit_type = (data.get("edit_type") or "").strip()
        return edit_type if edit_type in {"outline_edit", "description_edit", "image_edit"} else "description_edit"

    def _rewrite_outline_from_chat(
        self, page: dict[str, Any], user_message: str
    ) -> dict[str, Any]:
        outline = page.get("outline_content") or {}
        system_prompt = (
            "You rewrite slide outline content based on user instruction. "
            "Return ONLY valid JSON with keys title, points, assistant_message."
        )
        user_prompt = (
            f"Current title: {outline.get('title') or 'Untitled'}\n"
            f"Current points:\n{self._bullet_join(outline.get('points') or [])}\n\n"
            f"Instruction:\n{user_message}\n\n"
            "Rewrite the slide title and bullet points.\n"
            "- Keep title concise and presentation-ready.\n"
            "- Return 3-5 bullet points.\n"
            "- assistant_message should briefly confirm what was changed."
        )
        data = self._complete_json_sync(user_prompt, system_prompt)
        points = [str(point).strip() for point in (data.get("points") or []) if str(point).strip()]
        if not points:
            points = outline.get("points") or []
        title = (data.get("title") or "").strip() or outline.get("title") or "Untitled Slide"
        assistant_message = (data.get("assistant_message") or "").strip() or "已根据你的要求调整这一页的大纲，并开始重生成。"
        return {"title": title, "points": points, "assistant_message": assistant_message}

    def _rewrite_description_from_chat(
        self, page: dict[str, Any], user_message: str
    ) -> dict[str, Any]:
        outline = page.get("outline_content") or {}
        current_description = (
            (page.get("description_content") or {}).get("text")
            if isinstance(page.get("description_content"), dict)
            else ""
        )
        system_prompt = (
            "You rewrite slide description content based on user instruction. "
            "Return ONLY valid JSON with keys description_text, assistant_message."
        )
        user_prompt = (
            f"Slide title: {outline.get('title') or 'Untitled'}\n"
            f"Slide points:\n{self._bullet_join(outline.get('points') or [])}\n\n"
            f"Current description:\n{current_description or 'None'}\n\n"
            f"Instruction:\n{user_message}\n\n"
            "Write an updated single-slide description that the image generation pipeline can use."
        )
        data = self._complete_json_sync(user_prompt, system_prompt)
        description_text = (data.get("description_text") or "").strip()
        if not description_text:
            raise ValueError("Failed to derive updated description text from chat instruction")
        assistant_message = (data.get("assistant_message") or "").strip() or "已根据你的要求改写这一页内容，并开始重生成。"
        return {
            "description_text": description_text,
            "assistant_message": assistant_message,
        }

    def _rewrite_image_prompt_from_chat(
        self, page: dict[str, Any], user_message: str
    ) -> dict[str, Any]:
        outline = page.get("outline_content") or {}
        current_prompt = (page.get("image_prompt") or "").strip()
        system_prompt = (
            "You rewrite a slide image prompt based on user instruction. "
            "Return ONLY valid JSON with keys image_prompt, assistant_message."
        )
        user_prompt = (
            f"Slide title: {outline.get('title') or 'Untitled'}\n"
            f"Slide points:\n{self._bullet_join(outline.get('points') or [])}\n\n"
            f"Current image prompt:\n{current_prompt or 'None'}\n\n"
            f"Instruction:\n{user_message}\n\n"
            "Write one improved image prompt for a professional 16:9 presentation visual."
        )
        data = self._complete_json_sync(user_prompt, system_prompt)
        image_prompt = (data.get("image_prompt") or "").strip() or current_prompt
        if not image_prompt:
            raise ValueError("Failed to derive updated image prompt from chat instruction")
        assistant_message = (data.get("assistant_message") or "").strip() or "已根据你的要求调整图片方向，并开始重生成。"
        return {"image_prompt": image_prompt, "assistant_message": assistant_message}

    async def _complete_json_async(self, prompt: str, system_prompt: str) -> dict[str, Any]:
        llm_cfg = get_llm_config()
        kwargs = get_token_limit_kwargs(llm_cfg.model, 1200)
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
        data = self._extract_json(raw)
        if not data:
            raise ValueError("Failed to parse LLM JSON output")
        return data

    async def _derive_reference_style_prompt(self, image_path: Path) -> str:
        image_bytes = image_path.read_bytes()
        if not image_bytes:
            raise ReferenceStyleExtractionError("Reference image is empty")
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        mime_type = self._guess_image_content_type(image_path)
        system_prompt = (
            "You extract visual style guidance for PPT generation from a reference image. "
            "Return ONLY valid JSON with keys style_prompt, palette_hint, composition_hint."
        )
        user_text = (
            "Analyze this reference image and describe the PPT visual direction it implies. "
            "Focus on palette, layout rhythm, negative space, image treatment, texture, lighting, and typography mood. "
            "The style_prompt should be concise but specific enough to guide slide illustrations."
        )
        llm_cfg = get_llm_config()
        kwargs = get_token_limit_kwargs(llm_cfg.model, 1200)
        vision_model_func = get_llm_client().get_vision_model_func()
        raw = await vision_model_func(
            prompt="",
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{image_b64}",
                            },
                        },
                    ],
                },
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            **kwargs,
        )
        data = self._extract_json(raw)
        if not data:
            raise ReferenceStyleExtractionError("Failed to parse reference style JSON output")
        style_prompt = (data.get("style_prompt") or "").strip()
        palette_hint = (data.get("palette_hint") or "").strip()
        composition_hint = (data.get("composition_hint") or "").strip()
        if not style_prompt:
            raise ReferenceStyleExtractionError("Reference style response missing style_prompt")
        prompt_parts = [style_prompt]
        if palette_hint:
            prompt_parts.append(f"Palette hint: {palette_hint}")
        if composition_hint:
            prompt_parts.append(f"Composition hint: {composition_hint}")
        return "\n".join(prompt_parts)

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


_service: PptProjectService | None = None


def get_ppt_project_service(project_root: Path | None = None) -> PptProjectService:
    global _service
    if _service is None:
        if project_root is None:
            project_root = Path(__file__).resolve().parents[3]
        _service = PptProjectService(project_root)
    return _service
