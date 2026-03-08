from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import uuid

from sqlalchemy import delete, func, select, update

from .db import (
    get_engine,
    ppt_page_image_versions,
    ppt_pages,
    ppt_projects,
    ppt_tasks,
    utc_now,
)


def _new_id() -> str:
    return str(uuid.uuid4())


def _to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _project_row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "notebook_id": row.notebook_id,
        "session_id": row.session_id,
        "creation_type": row.creation_type,
        "idea_prompt": row.idea_prompt,
        "outline_text": row.outline_text,
        "description_text": row.description_text,
        "source_content": row.source_content,
        "template_style": row.template_style,
        "template_image_path": row.template_image_path,
        "reference_style_prompt": row.reference_style_prompt,
        "image_aspect_ratio": row.image_aspect_ratio,
        "language": row.language,
        "reference_sources": row.reference_sources or [],
        "status": row.status,
        "created_at": _to_iso(row.created_at),
        "updated_at": _to_iso(row.updated_at),
    }


def _page_row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "order_index": row.order_index,
        "part": row.part,
        "outline_content": row.outline_content or {},
        "description_content": row.description_content,
        "image_prompt": row.image_prompt,
        "generated_image_path": row.generated_image_path,
        "cached_image_path": row.cached_image_path,
        "status": row.status,
        "created_at": _to_iso(row.created_at),
        "updated_at": _to_iso(row.updated_at),
    }


def _task_row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "task_type": row.task_type,
        "status": row.status,
        "progress": row.progress or {},
        "error_message": row.error_message,
        "created_at": _to_iso(row.created_at),
        "updated_at": _to_iso(row.updated_at),
        "finished_at": _to_iso(row.finished_at),
    }


def _image_version_row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "page_id": row.page_id,
        "version_number": row.version_number,
        "image_path": row.image_path,
        "cached_image_path": row.cached_image_path,
        "prompt_used": row.prompt_used,
        "is_current": row.is_current,
        "created_at": _to_iso(row.created_at),
    }


def create_project(
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
    status: str,
) -> dict[str, Any]:
    project_id = _new_id()
    now = utc_now()
    stmt = ppt_projects.insert().values(
        id=project_id,
        notebook_id=notebook_id,
        session_id=session_id,
        creation_type=creation_type,
        idea_prompt=idea_prompt,
        outline_text=outline_text,
        description_text=description_text,
        source_content=source_content,
        template_style=template_style,
        template_image_path=template_image_path,
        reference_style_prompt=reference_style_prompt,
        image_aspect_ratio=image_aspect_ratio,
        language=language,
        reference_sources=reference_sources or [],
        status=status,
        created_at=now,
        updated_at=now,
    )
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(stmt)
        row = conn.execute(select(ppt_projects).where(ppt_projects.c.id == project_id)).first()
    return _project_row_to_dict(row)


def get_project(project_id: str) -> dict[str, Any] | None:
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(select(ppt_projects).where(ppt_projects.c.id == project_id)).first()
    return _project_row_to_dict(row) if row else None


def update_project(project_id: str, **fields: Any) -> dict[str, Any] | None:
    if not fields:
        return get_project(project_id)
    fields["updated_at"] = utc_now()
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(update(ppt_projects).where(ppt_projects.c.id == project_id).values(**fields))
        row = conn.execute(select(ppt_projects).where(ppt_projects.c.id == project_id)).first()
    return _project_row_to_dict(row) if row else None


def list_pages(project_id: str) -> list[dict[str, Any]]:
    engine = get_engine()
    with engine.begin() as conn:
        rows = conn.execute(
            select(ppt_pages)
            .where(ppt_pages.c.project_id == project_id)
            .order_by(ppt_pages.c.order_index.asc(), ppt_pages.c.created_at.asc())
        ).all()
    return [_page_row_to_dict(row) for row in rows]


def get_page(page_id: str) -> dict[str, Any] | None:
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(select(ppt_pages).where(ppt_pages.c.id == page_id)).first()
    return _page_row_to_dict(row) if row else None


def create_page(
    *,
    project_id: str,
    order_index: int,
    part: str | None,
    outline_content: dict[str, Any],
    description_content: dict[str, Any] | None = None,
    image_prompt: str | None = None,
    generated_image_path: str | None = None,
    cached_image_path: str | None = None,
    status: str = "DRAFT",
) -> dict[str, Any]:
    page_id = _new_id()
    now = utc_now()
    stmt = ppt_pages.insert().values(
        id=page_id,
        project_id=project_id,
        order_index=order_index,
        part=part,
        outline_content=outline_content,
        description_content=description_content,
        image_prompt=image_prompt,
        generated_image_path=generated_image_path,
        cached_image_path=cached_image_path,
        status=status,
        created_at=now,
        updated_at=now,
    )
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(stmt)
        row = conn.execute(select(ppt_pages).where(ppt_pages.c.id == page_id)).first()
    return _page_row_to_dict(row)


def update_page(page_id: str, **fields: Any) -> dict[str, Any] | None:
    if not fields:
        return get_page(page_id)
    fields["updated_at"] = utc_now()
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(update(ppt_pages).where(ppt_pages.c.id == page_id).values(**fields))
        row = conn.execute(select(ppt_pages).where(ppt_pages.c.id == page_id)).first()
    return _page_row_to_dict(row) if row else None


def delete_pages(page_ids: list[str]) -> None:
    if not page_ids:
        return
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            delete(ppt_page_image_versions).where(ppt_page_image_versions.c.page_id.in_(page_ids))
        )
        conn.execute(delete(ppt_pages).where(ppt_pages.c.id.in_(page_ids)))


def create_task(
    project_id: str,
    task_type: str,
    *,
    status: str = "PENDING",
    progress: dict[str, Any] | None = None,
) -> dict[str, Any]:
    task_id = _new_id()
    now = utc_now()
    stmt = ppt_tasks.insert().values(
        id=task_id,
        project_id=project_id,
        task_type=task_type,
        status=status,
        progress=progress or {},
        error_message=None,
        created_at=now,
        updated_at=now,
        finished_at=None,
    )
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(stmt)
        row = conn.execute(select(ppt_tasks).where(ppt_tasks.c.id == task_id)).first()
    return _task_row_to_dict(row)


def get_task(project_id: str, task_id: str) -> dict[str, Any] | None:
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            select(ppt_tasks)
            .where(ppt_tasks.c.id == task_id)
            .where(ppt_tasks.c.project_id == project_id)
        ).first()
    return _task_row_to_dict(row) if row else None


def list_tasks(project_id: str) -> list[dict[str, Any]]:
    engine = get_engine()
    with engine.begin() as conn:
        rows = conn.execute(
            select(ppt_tasks)
            .where(ppt_tasks.c.project_id == project_id)
            .order_by(ppt_tasks.c.created_at.desc())
        ).all()
    return [_task_row_to_dict(row) for row in rows]


def update_task(task_id: str, **fields: Any) -> dict[str, Any] | None:
    if not fields:
        return None
    status = fields.get("status")
    fields["updated_at"] = utc_now()
    if status in {"COMPLETED", "FAILED", "CANCELED"}:
        fields["finished_at"] = utc_now()
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(update(ppt_tasks).where(ppt_tasks.c.id == task_id).values(**fields))
        row = conn.execute(select(ppt_tasks).where(ppt_tasks.c.id == task_id)).first()
    return _task_row_to_dict(row) if row else None


def get_next_page_image_version(page_id: str) -> int:
    engine = get_engine()
    with engine.begin() as conn:
        value = conn.execute(
            select(func.max(ppt_page_image_versions.c.version_number)).where(
                ppt_page_image_versions.c.page_id == page_id
            )
        ).scalar()
    return int(value or 0) + 1


def create_page_image_version(
    *,
    page_id: str,
    version_number: int,
    image_path: str,
    cached_image_path: str | None,
    prompt_used: str | None,
    is_current: bool = True,
) -> dict[str, Any]:
    version_id = _new_id()
    now = utc_now()
    engine = get_engine()
    with engine.begin() as conn:
        if is_current:
            conn.execute(
                update(ppt_page_image_versions)
                .where(ppt_page_image_versions.c.page_id == page_id)
                .values(is_current=False)
            )
        conn.execute(
            ppt_page_image_versions.insert().values(
                id=version_id,
                page_id=page_id,
                version_number=version_number,
                image_path=image_path,
                cached_image_path=cached_image_path,
                prompt_used=prompt_used,
                is_current=is_current,
                created_at=now,
            )
        )
        row = conn.execute(
            select(ppt_page_image_versions).where(ppt_page_image_versions.c.id == version_id)
        ).first()
    return _image_version_row_to_dict(row)


def list_page_image_versions(page_id: str) -> list[dict[str, Any]]:
    engine = get_engine()
    with engine.begin() as conn:
        rows = conn.execute(
            select(ppt_page_image_versions)
            .where(ppt_page_image_versions.c.page_id == page_id)
            .order_by(ppt_page_image_versions.c.version_number.desc())
        ).all()
    return [_image_version_row_to_dict(row) for row in rows]


def activate_page_image_version(page_id: str, version_number: int) -> dict[str, Any] | None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            update(ppt_page_image_versions)
            .where(ppt_page_image_versions.c.page_id == page_id)
            .values(is_current=False)
        )
        conn.execute(
            update(ppt_page_image_versions)
            .where(ppt_page_image_versions.c.page_id == page_id)
            .where(ppt_page_image_versions.c.version_number == version_number)
            .values(is_current=True)
        )
        row = conn.execute(
            select(ppt_page_image_versions)
            .where(ppt_page_image_versions.c.page_id == page_id)
            .where(ppt_page_image_versions.c.version_number == version_number)
        ).first()
    return _image_version_row_to_dict(row) if row else None


def get_project_bundle(project_id: str) -> dict[str, Any] | None:
    project = get_project(project_id)
    if not project:
        return None
    project["pages"] = list_pages(project_id)
    project["tasks"] = list_tasks(project_id)
    return project
