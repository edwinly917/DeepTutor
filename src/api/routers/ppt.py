from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from src.services.export.ppt_project_service import (
    ReferenceImageValidationError,
    ReferenceStyleExtractionError,
    get_ppt_project_service,
)

router = APIRouter()


def _service():
    project_root = Path(__file__).resolve().parents[3]
    return get_ppt_project_service(project_root)


class CreatePptProjectRequest(BaseModel):
    notebook_id: str | None = None
    session_id: str | None = None
    creation_type: Literal["idea", "outline", "descriptions"]
    idea_prompt: str | None = None
    outline_text: str | None = None
    description_text: str | None = None
    source_content: str | None = None
    template_style: str | None = None
    template_image_path: str | None = None
    reference_style_prompt: str | None = None
    image_aspect_ratio: Literal["16:9", "4:3"] = "16:9"
    language: str = "zh"
    reference_sources: list[dict[str, Any]] = Field(default_factory=list)


class GenerateOutlineRequest(BaseModel):
    style_prompt: str | None = None
    max_slides: int | None = None


class GenerateDescriptionsRequest(BaseModel):
    page_ids: list[str] | None = None
    detail_level: Literal["concise", "default", "detailed"] = "default"


class GenerateImagesRequest(BaseModel):
    page_ids: list[str] | None = None


class UpdatePageRequest(BaseModel):
    title: str | None = None
    points: list[str] | None = None
    description_text: str | None = None
    image_prompt: str | None = None


class DeriveIdeaRequest(BaseModel):
    source_content: str


class DeriveOutlineRequest(BaseModel):
    source_content: str
    style_prompt: str | None = None
    max_slides: int | None = None


class StylePreviewRequest(BaseModel):
    style_prompt: str | None = None


@router.get("/config")
async def get_ppt_config():
    return _service().get_config()


@router.post("/reference-images")
async def upload_reference_image(file: UploadFile = File(...)):
    try:
        payload = await _service().upload_reference_image(
            filename=file.filename or "reference-image.png",
            content_type=file.content_type,
            data=await file.read(),
        )
        return payload
    except ReferenceImageValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ReferenceStyleExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/helpers/derive-idea")
async def derive_idea(request: DeriveIdeaRequest):
    try:
        return await _service().derive_idea(request.source_content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/helpers/derive-outline")
async def derive_outline(request: DeriveOutlineRequest):
    try:
        return await _service().derive_outline(
            request.source_content,
            style_prompt=request.style_prompt,
            max_slides=request.max_slides,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/style-preview")
async def preview_style(request: StylePreviewRequest):
    try:
        return await _service().preview_style(request.style_prompt)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/projects")
async def create_project(request: CreatePptProjectRequest):
    try:
        return _service().create_project(**request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/projects/{project_id}")
async def get_project(project_id: str):
    project = _service().get_project_bundle(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.post("/projects/{project_id}/generate/outline")
async def generate_outline(project_id: str, request: GenerateOutlineRequest):
    try:
        return await _service().generate_outline(
            project_id,
            style_prompt=request.style_prompt,
            max_slides=request.max_slides,
        )
    except ValueError as exc:
        status = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/projects/{project_id}/generate/descriptions")
async def generate_descriptions(project_id: str, request: GenerateDescriptionsRequest):
    try:
        return _service().start_generate_descriptions(
            project_id,
            page_ids=request.page_ids,
            detail_level=request.detail_level,
        )
    except ValueError as exc:
        status = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/projects/{project_id}/generate/images")
async def generate_images(project_id: str, request: GenerateImagesRequest):
    try:
        return _service().start_generate_images(project_id, page_ids=request.page_ids)
    except ValueError as exc:
        status = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/projects/{project_id}/tasks/{task_id}")
async def get_task(project_id: str, task_id: str):
    task = _service().get_task(project_id, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.put("/projects/{project_id}/pages/{page_id}")
async def update_page(project_id: str, page_id: str, request: UpdatePageRequest):
    try:
        return _service().update_page(project_id, page_id, **request.model_dump())
    except ValueError as exc:
        status = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/projects/{project_id}/pages/{page_id}/regenerate-image")
async def regenerate_page_image(project_id: str, page_id: str):
    try:
        return _service().start_regenerate_page_image(project_id, page_id)
    except ValueError as exc:
        status = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/projects/{project_id}/pages/{page_id}/image-versions")
async def list_image_versions(project_id: str, page_id: str):
    try:
        return {"versions": _service().list_image_versions(project_id, page_id)}
    except ValueError as exc:
        status = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/projects/{project_id}/pages/{page_id}/image-versions/{version_number}/activate")
async def activate_image_version(project_id: str, page_id: str, version_number: int):
    try:
        version = _service().activate_image_version(project_id, page_id, version_number)
        return {"version": version}
    except ValueError as exc:
        status = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/projects/{project_id}/export/pptx")
async def export_pptx(project_id: str, page_ids: list[str] | None = Query(default=None)):
    try:
        return _service().export_pptx(project_id, page_ids=page_ids)
    except ValueError as exc:
        status = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status, detail=str(exc))
    except ImportError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/projects/{project_id}/export/pdf")
async def export_pdf(project_id: str, page_ids: list[str] | None = Query(default=None)):
    try:
        return _service().export_pdf(project_id, page_ids=page_ids)
    except ValueError as exc:
        status = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/projects/{project_id}/export/editable-pptx")
async def export_editable_pptx(project_id: str):
    raise HTTPException(status_code=501, detail="NOT_IMPLEMENTED_PHASE2")
