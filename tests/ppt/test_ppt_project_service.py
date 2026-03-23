from __future__ import annotations

from typing import Any

import pytest

from src.services.storage import ppt_store


def test_from_notebook_project_persists_record_ids_and_freezes_selected_records(
    ppt_service, monkeypatch
):
    notebook = {
        "id": "nb-1",
        "records": [
            {
                "id": "record-a",
                "type": "note",
                "title": "Alpha",
                "user_query": "alpha query",
                "output": "Alpha output",
                "metadata": {},
                "created_at": 1,
            },
            {
                "id": "record-b",
                "type": "research",
                "title": "Beta",
                "user_query": "beta query",
                "output": "Beta output",
                "metadata": {},
                "created_at": 2,
            },
        ],
    }

    monkeypatch.setattr(
        "src.services.ppt.content_extractors.NotebookManager.get_notebook",
        lambda self, notebook_id: notebook if notebook_id == "nb-1" else None,
    )

    bundle = ppt_service.create_project(
        notebook_id="nb-1",
        session_id=None,
        creation_type="from_notebook",
        source_content=None,
        style_preset_id=None,
        style_custom_text=None,
        template_image_path=None,
        template_file_refs=[],
        reference_style_prompt=None,
        reference_layout_prompt=None,
        reference_content_prompt=None,
        image_aspect_ratio="16:9",
        language="zh",
        reference_sources=[],
        source_refs=[],
        record_ids=["record-b"],
    )

    assert bundle["record_ids"] == ["record-b"]
    assert "Beta output" in (bundle["source_content"] or "")
    assert "Alpha output" not in (bundle["source_content"] or "")

    stored = ppt_store.get_project(bundle["id"])
    assert stored is not None
    assert stored["record_ids"] == ["record-b"]
    assert "Beta output" in (stored["source_content"] or "")
    assert "Alpha output" not in (stored["source_content"] or "")


def test_from_sources_project_freezes_report_snapshot_by_value(ppt_service):
    source_refs = [
        {
            "type": "report",
            "title": "Research Report",
            "source_key": "session:abc123",
            "content": "original frozen report",
        }
    ]

    bundle = ppt_service.create_project(
        notebook_id="nb-1",
        session_id="session-1",
        creation_type="from_sources",
        source_content=None,
        style_preset_id=None,
        style_custom_text=None,
        template_image_path=None,
        template_file_refs=[],
        reference_style_prompt=None,
        reference_layout_prompt=None,
        reference_content_prompt=None,
        image_aspect_ratio="16:9",
        language="zh",
        reference_sources=[],
        source_refs=source_refs,
        record_ids=[],
    )

    source_refs[0]["content"] = "mutated later"
    stored = ppt_store.get_project(bundle["id"])
    assert stored is not None
    assert stored["source_refs"][0]["content"] == "original frozen report"


def test_update_page_marks_dirty_and_regenerate_page_refreshes_description_prompt_and_image(
    ppt_service, monkeypatch
):
    project = ppt_store.create_project(
        notebook_id="nb-1",
        session_id=None,
        creation_type="from_sources",
        idea_prompt=None,
        outline_text=None,
        description_text="seed",
        source_content="seed",
        style_preset_id=None,
        style_custom_text=None,
        template_image_path=None,
        template_file_refs=[],
        reference_style_prompt=None,
        reference_layout_prompt=None,
        reference_content_prompt=None,
        image_aspect_ratio="16:9",
        language="zh",
        reference_sources=[],
        status="IMAGE_READY",
    )
    page = ppt_store.create_page(
        project_id=project["id"],
        order_index=0,
        part=None,
        outline_content={"title": "Old title", "points": ["Old point"]},
        description_content={"text": "Old description"},
        image_prompt="old image prompt",
        generated_image_path="slides/old.png",
        cached_image_path="slides/old-thumb.jpg",
        is_dirty=False,
        status="IMAGE_READY",
    )

    updated = ppt_service.update_page(
        project["id"],
        page["id"],
        title="New title",
        description_text="Fresh user edit",
    )
    assert updated["is_dirty"] is True
    assert updated["status"] == "DRAFT"

    async def fake_prepare(
        project_id: str, project_payload: dict[str, Any]
    ) -> tuple[dict[str, Any], list[str]]:
        return project_payload, []

    async def fake_ensure_analysis(project_payload: dict[str, Any]) -> dict[str, Any]:
        return project_payload

    monkeypatch.setattr(ppt_service, "_prepare_project_source_content", fake_prepare)
    monkeypatch.setattr(ppt_service, "_ensure_template_analysis", fake_ensure_analysis)
    monkeypatch.setattr(
        ppt_service,
        "_filter_pages",
        lambda project_id, page_ids: [ppt_store.get_page(page["id"])],
    )
    monkeypatch.setattr(ppt_service, "_resolve_project_title", lambda project_payload: "Deck Title")
    monkeypatch.setattr(
        ppt_service,
        "_generate_page_description",
        lambda project_payload, page_payload, detail_level, deck_outline_summary, style_context: {
            "description_content": {"text": "Fresh generated description"},
            "image_prompt": "fresh generated image prompt",
        },
    )
    monkeypatch.setattr(
        ppt_service,
        "_generate_page_image",
        lambda project_payload, page_payload, style_context, deck_title: {
            "generated_image_path": "slides/new.png",
            "cached_image_path": "slides/new-thumb.jpg",
            "prompt_used": page_payload.get("image_prompt") or "fresh generated image prompt",
        },
    )

    def run_inline(task_id, func, *args, **kwargs):
        func(task_id, *args, **kwargs)

    monkeypatch.setattr(
        "src.services.ppt.orchestrator.ppt_task_manager.submit",
        run_inline,
    )

    task = ppt_service.start_regenerate_page_image(project["id"], page["id"])

    refreshed = ppt_store.get_page(page["id"])
    assert refreshed is not None
    assert refreshed["is_dirty"] is False
    assert refreshed["status"] == "IMAGE_READY"
    assert refreshed["outline_content"]["title"] == "New title"
    assert refreshed["description_content"]["text"] == "Fresh generated description"
    assert refreshed["image_prompt"] == "fresh generated image prompt"
    assert refreshed["generated_image_path"] == "slides/new.png"

    stored_task = ppt_store.get_task(project["id"], task["id"])
    assert stored_task is not None
    assert stored_task["status"] == "COMPLETED"
    versions = ppt_store.list_page_image_versions(page["id"])
    assert len(versions) == 1
    assert versions[0]["image_path"] == "slides/new.png"


def test_export_pptx_rejects_dirty_pages(ppt_service):
    project = ppt_store.create_project(
        notebook_id="nb-1",
        session_id=None,
        creation_type="from_sources",
        idea_prompt=None,
        outline_text=None,
        description_text="seed",
        source_content="seed",
        style_preset_id=None,
        style_custom_text=None,
        template_image_path=None,
        template_file_refs=[],
        reference_style_prompt=None,
        reference_layout_prompt=None,
        reference_content_prompt=None,
        image_aspect_ratio="16:9",
        language="zh",
        reference_sources=[],
        status="IMAGE_READY",
    )
    ppt_store.create_page(
        project_id=project["id"],
        order_index=0,
        part=None,
        outline_content={"title": "Slide"},
        description_content={"text": "Desc"},
        generated_image_path="slides/existing.png",
        cached_image_path="slides/existing-thumb.jpg",
        is_dirty=True,
        status="DRAFT",
    )

    with pytest.raises(ValueError, match="pending regeneration"):
        ppt_service.export_pptx(project["id"])
