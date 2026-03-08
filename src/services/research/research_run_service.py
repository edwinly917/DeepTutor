from __future__ import annotations

from pathlib import Path
import time
from typing import Any

from src.api.utils.notebook_manager import notebook_manager
from src.logging import get_logger
from src.services.storage import research_store

from .run_config import (
    build_dedupe_key,
    build_effective_research_config,
    build_research_paths,
    generate_research_id,
)

logger = get_logger("ResearchRunService")


class ResearchRunService:
    def __init__(self, project_root: Path):
        self.project_root = project_root

    def create_or_attach_run(
        self,
        *,
        notebook_id: str | None,
        session_id: str | None,
        topic: str,
        kb_name: str | None,
        plan_mode: str,
        enabled_tools: list[str] | None,
        skip_rephrase: bool,
        preset: str | None = None,
        research_mode: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        dedupe_key = build_dedupe_key(
            notebook_id=notebook_id, session_id=session_id, kb_name=kb_name, topic=topic
        )
        existing = research_store.find_active_run_by_dedupe_key(dedupe_key)
        if existing:
            return existing, True

        config_snapshot = build_effective_research_config(
            project_root=self.project_root,
            kb_name=kb_name,
            plan_mode=plan_mode,
            enabled_tools=enabled_tools,
            skip_rephrase=skip_rephrase,
            preset=preset,
            research_mode=research_mode,
        )
        tools = list(dict.fromkeys((enabled_tools or ["RAG"]) + ["Web"]))
        run = research_store.create_run(
            research_id=generate_research_id(),
            notebook_id=notebook_id,
            session_id=session_id,
            dedupe_key=dedupe_key,
            topic=topic,
            kb_name=kb_name,
            plan_mode=plan_mode,
            enabled_tools=tools,
            config_snapshot=config_snapshot,
            progress={"current": 0, "total": 0, "message": "queued"},
            checkpoint={
                "topic": topic,
                "planning_completed": False,
                "researching_completed": False,
                "reporting_completed": False,
                "completed_section_keys": [],
            },
        )
        self.append_event(
            run["id"],
            {
                "type": "status",
                "content": "started",
                "research_id": run["research_id"],
                "run_id": run["id"],
            },
            stage="PLANNING",
        )
        return run, False

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        return research_store.get_run(run_id)

    def get_run_by_research_id(self, research_id: str) -> dict[str, Any] | None:
        return research_store.get_run_by_research_id(research_id)

    def list_events(
        self, run_id: str, *, after_id: int = 0, limit: int = 500
    ) -> list[dict[str, Any]]:
        return research_store.list_events(run_id, after_id=after_id, limit=limit)

    def cancel_run(self, run_id: str) -> dict[str, Any] | None:
        run = research_store.cancel_run(run_id)
        if run:
            self.append_event(
                run_id,
                {
                    "type": "status",
                    "content": "cancel_requested",
                    "research_id": run["research_id"],
                    "run_id": run_id,
                },
                stage=run.get("phase") or "RUNNING",
            )
        return run

    def append_event(
        self, run_id: str, payload: dict[str, Any], *, stage: str | None = None
    ) -> dict[str, Any]:
        event_type = str(payload.get("type") or "event")
        stored = research_store.append_event(
            run_id, event_type=event_type, stage=stage, payload=payload
        )
        update_fields: dict[str, Any] = {}
        progress = self._progress_from_payload(payload)
        if progress is not None:
            update_fields["progress"] = progress
        phase = self._phase_from_payload(payload)
        if phase is not None:
            update_fields["phase"] = phase
        if update_fields:
            research_store.update_run(run_id, **update_fields)
        return stored

    def mark_phase_checkpoint(
        self,
        run_id: str,
        *,
        phase: str,
        checkpoint_patch: dict[str, Any] | None = None,
        progress: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        run = research_store.get_run(run_id)
        if not run:
            return None
        checkpoint = dict(run.get("checkpoint") or {})
        checkpoint.update(checkpoint_patch or {})
        fields: dict[str, Any] = {"phase": phase, "checkpoint": checkpoint}
        if progress is not None:
            fields["progress"] = progress
        return research_store.update_run(run_id, **fields)

    def mark_completed(
        self,
        run_id: str,
        *,
        report_path: str,
        metadata_path: str,
        report_content: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any] | None:
        run = research_store.update_run(
            run_id,
            status="COMPLETED",
            phase="SAVING",
            report_path=report_path,
            metadata_path=metadata_path,
            error_message=None,
            checkpoint={
                **(research_store.get_run(run_id) or {}).get("checkpoint", {}),
                "reporting_completed": True,
            },
        )
        if run:
            self.append_event(
                run_id,
                {
                    "type": "report_path",
                    "path": report_path,
                    "research_id": run["research_id"],
                    "run_id": run_id,
                },
                stage="SAVING",
            )
            self.append_event(
                run_id,
                {
                    "type": "result",
                    "report": report_content,
                    "metadata": metadata,
                    "research_id": run["research_id"],
                    "run_id": run_id,
                },
                stage="SAVING",
            )
            self.persist_successful_session(run, report_content, metadata)
        return run

    def mark_failed(self, run_id: str, error_message: str) -> dict[str, Any] | None:
        run = research_store.update_run(run_id, status="FAILED", error_message=error_message)
        if run:
            self.append_event(
                run_id,
                {
                    "type": "error",
                    "content": error_message,
                    "research_id": run["research_id"],
                    "run_id": run_id,
                },
                stage=run.get("phase") or "RUNNING",
            )
            self.clear_session_state(run, error_message=error_message)
        return run

    def mark_cancelled(self, run_id: str) -> dict[str, Any] | None:
        run = research_store.update_run(run_id, status="CANCELLED", error_message="cancelled")
        if run:
            self.append_event(
                run_id,
                {
                    "type": "error",
                    "content": "研究任务已取消",
                    "research_id": run["research_id"],
                    "run_id": run_id,
                },
                stage=run.get("phase") or "RUNNING",
            )
            self.clear_session_state(run, error_message="研究任务已取消")
        return run

    def clear_session_state(self, run: dict[str, Any], *, error_message: str | None = None) -> None:
        notebook_id = run.get("notebook_id")
        session_id = run.get("session_id")
        if not notebook_id or not session_id:
            return
        try:
            sessions = notebook_manager.list_sessions(notebook_id)
            existing = next((s for s in sessions if s.get("session_id") == session_id), None)
            if not existing:
                return
            updated = dict(existing)
            updated["research_state"] = None
            updated["updated_at"] = time.time()
            if error_message:
                messages = list(updated.get("messages") or [])
                patched = False
                for message in reversed(messages):
                    if message.get("role") == "assistant" and message.get("isStreaming"):
                        message["content"] = f"❌ 深度研究已中断：{error_message}"
                        message["isStreaming"] = False
                        patched = True
                        break
                if not patched:
                    messages.append(
                        {
                            "id": f"research-error-{int(time.time() * 1000)}",
                            "role": "assistant",
                            "content": f"❌ 深度研究已中断：{error_message}",
                            "isStreaming": False,
                        }
                    )
                updated["messages"] = messages
            notebook_manager.upsert_session(notebook_id, updated)
        except Exception as exc:
            logger.warning(f"Failed to clear notebook research state: {exc}")

    def persist_successful_session(
        self, run: dict[str, Any], report_content: str, metadata: dict[str, Any] | None = None
    ) -> None:
        notebook_id = run.get("notebook_id")
        session_id = run.get("session_id")
        topic = run.get("topic") or ""
        if not notebook_id or not session_id:
            return
        try:
            sessions = notebook_manager.list_sessions(notebook_id)
            existing = next((s for s in sessions if s.get("session_id") == session_id), None)
            if not existing:
                return
            updated = dict(existing)
            updated["research_report"] = report_content
            updated["research_state"] = None
            updated["updated_at"] = time.time()
            sources = list(updated.get("sources", []) or [])

            def source_key(item: dict) -> str:
                return f"{item.get('type')}-{item.get('url') or item.get('title') or item.get('id') or ''}"

            existing_keys = {source_key(item) for item in sources}

            def add_source(item: dict) -> None:
                key = source_key(item)
                if key in existing_keys:
                    return
                existing_keys.add(key)
                sources.append(item)

            if report_content:
                title = f"深度研究报告 - {topic}" if topic else "深度研究报告"
                sources = [item for item in sources if item.get("type") != "report"]
                existing_keys = {source_key(item) for item in sources}
                add_source(
                    {
                        "id": f"report-{int(time.time() * 1000)}",
                        "type": "report",
                        "title": title,
                        "selected": True,
                        "content": report_content,
                    }
                )

            metadata = metadata or {}
            for idx, source in enumerate(metadata.get("web_sources") or []):
                add_source(
                    {
                        "id": f"research-web-{int(time.time() * 1000)}-{idx}",
                        "type": "web",
                        "title": source.get("title") or source.get("url") or f"网络来源 {idx + 1}",
                        "url": source.get("url") or "",
                        "content": source.get("content") or source.get("snippet") or "",
                        "selected": True,
                        "source_key": source.get("source_key"),
                        "ref_number": source.get("ref_number"),
                    }
                )
            for idx, source in enumerate(metadata.get("rag_sources") or []):
                add_source(
                    {
                        "id": f"research-rag-{int(time.time() * 1000)}-{idx}",
                        "type": "kb",
                        "title": source.get("title")
                        or source.get("source")
                        or source.get("source_file")
                        or source.get("kb_name")
                        or f"知识库来源 {idx + 1}",
                        "url": source.get("url") or "",
                        "content": source.get("content") or source.get("content_preview") or "",
                        "selected": True,
                        "source_key": source.get("source_key"),
                        "ref_number": source.get("ref_number"),
                    }
                )
            updated["sources"] = sources
            notebook_manager.upsert_session(notebook_id, updated)
        except Exception as exc:
            logger.warning(f"Failed to persist successful research session: {exc}")

    def research_paths(self, research_id: str) -> dict[str, Path]:
        return build_research_paths(self.project_root, research_id)

    @staticmethod
    def _progress_from_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
        if payload.get("type") != "progress":
            return None
        status = str(payload.get("status") or "")
        stage = str(payload.get("stage") or "").lower()
        if stage == "researching":
            current = int(payload.get("current_block") or payload.get("completed_count") or 0)
            total = int(payload.get("total_blocks") or 0)
            message = str(payload.get("sub_topic") or status or "researching")
            return {"current": current, "total": total, "message": message, "stage": stage}
        if stage == "reporting":
            section_index = payload.get("section_index")
            total_sections = payload.get("total_sections")
            current = int(section_index) + 1 if section_index is not None else 0
            total = int(total_sections or 0)
            message = str(payload.get("current_section") or status or "reporting")
            return {"current": current, "total": total, "message": message, "stage": stage}
        if stage == "planning":
            total = int(payload.get("total_blocks") or payload.get("generated_subtopics") or 0)
            return {"current": 0, "total": total, "message": status or "planning", "stage": stage}
        return {"current": 0, "total": 0, "message": status or "queued", "stage": stage or "idle"}

    @staticmethod
    def _phase_from_payload(payload: dict[str, Any]) -> str | None:
        if payload.get("type") == "result":
            return "SAVING"
        stage = str(payload.get("stage") or "").upper()
        if stage in {"PLANNING", "RESEARCHING", "REPORTING", "SAVING"}:
            return stage
        status = str(payload.get("content") or "").lower()
        if status == "started":
            return "PLANNING"
        return None


_service: ResearchRunService | None = None


def get_research_run_service(project_root: Path) -> ResearchRunService:
    global _service
    if _service is None or _service.project_root != project_root:
        _service = ResearchRunService(project_root)
    return _service
