from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.api.utils.notebook_manager import NotebookManager
from src.services.export.source_report import SourceReportGenerator

_NOTEBOOK_RECORD_CHAR_LIMIT = 2400
_NOTEBOOK_TOTAL_CHAR_LIMIT = 14000


class ResearchExtractor:
    def freeze_project_input(
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
        session = self.resolve_notebook_session(notebook_id, session_id)
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

    def resolve_notebook_session(
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


class NotebookExtractor:
    def freeze_project_input(
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
        return self.normalize_records(records)

    def normalize_records(self, records: list[dict[str, Any]]) -> str:
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

    def _trim_text(self, value: str, max_chars: int) -> str:
        text = (value or "").strip()
        if len(text) <= max_chars:
            return text
        return text[: max_chars - 1].rstrip() + "…"


class SourcesExtractor:
    def __init__(self) -> None:
        self.generator = SourceReportGenerator()

    async def generate_markdown(
        self,
        *,
        source_refs: list[dict[str, Any]],
        topic: str | None,
    ) -> tuple[str, list[str], datetime]:
        if not source_refs:
            raise ValueError("from_sources requires frozen source_refs")
        result = await self.generator.generate(
            sources=[dict(item) for item in source_refs],
            topic=topic,
        )
        markdown = (result.get("markdown") or "").strip()
        if not markdown:
            raise ValueError("No synthesized markdown was produced from selected sources")
        warnings = self.format_skipped_source_warnings(result.get("skipped_sources") or [])
        return markdown, warnings, datetime.now(timezone.utc)

    def format_skipped_source_warnings(self, skipped_sources: list[dict[str, Any]]) -> list[str]:
        warnings: list[str] = []
        for source in skipped_sources:
            title = (source.get("title") or "Untitled source").strip()
            reason = (source.get("reason") or "skipped").strip()
            warnings.append(f"Skipped source: {title} ({reason})")
        return warnings
