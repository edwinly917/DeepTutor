import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.agents.research.agents.reporting_agent import ReportingAgent
from src.agents.research.data_structures import TopicBlock
from src.api.routers import research as research_router
from src.services.research import research_run_service as run_service_module
from src.services.research.research_run_service import get_research_run_service
from src.services.storage import db as db_module


class _DummyResearchService:
    def __init__(self, run=None):
        self._run = run

    def get_run_by_research_id(self, research_id: str):
        return self._run


def _init_sqlite_db(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'research.db'}")
    if db_module._engine is not None:
        db_module._engine.dispose()
    db_module._engine = None
    db_module.init_db()
    run_service_module._service = None


def test_research_run_service_deduplicates_active_runs(monkeypatch, tmp_path):
    _init_sqlite_db(monkeypatch, tmp_path)
    service = get_research_run_service(project_root)

    first_run, attached_existing = service.create_or_attach_run(
        notebook_id="nb-1",
        session_id="session-1",
        topic="GLM5 模型调研",
        kb_name="DE-all",
        plan_mode="deep",
        enabled_tools=["RAG", "Web"],
        skip_rephrase=False,
    )
    second_run, second_attached = service.create_or_attach_run(
        notebook_id="nb-1",
        session_id="session-1",
        topic="GLM5 模型调研",
        kb_name="DE-all",
        plan_mode="deep",
        enabled_tools=["RAG", "Web"],
        skip_rephrase=False,
    )

    events = service.list_events(first_run["id"])

    assert attached_existing is False
    assert second_attached is True
    assert second_run["id"] == first_run["id"]
    assert first_run["status"] == "PENDING"
    assert len(events) == 1
    assert events[0]["payload"]["type"] == "status"
    assert events[0]["payload"]["content"] == "started"


def test_research_status_prefers_durable_run(monkeypatch, tmp_path):
    research_id = "research_20260308_000001"
    reports_dir = tmp_path / "data" / "user" / "research" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"{research_id}.md"
    metadata_path = reports_dir / f"{research_id}_metadata.json"
    report_path.write_text("# Test report", encoding="utf-8")
    metadata_path.write_text(
        json.dumps({"topic": "GLM5 模型调研", "completed_at": datetime.now().isoformat()}),
        encoding="utf-8",
    )

    run = {
        "id": "run-1",
        "research_id": research_id,
        "status": "COMPLETED",
        "phase": "SAVING",
        "progress": {"current": 3, "total": 3, "message": "done"},
        "checkpoint": {"reporting_completed": True},
        "report_path": str(report_path),
        "metadata_path": str(metadata_path),
        "error_message": None,
    }

    monkeypatch.setattr(research_router, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(
        research_router,
        "_research_service",
        lambda: _DummyResearchService(run=run),
    )

    result = asyncio.run(research_router.research_status(research_id))

    assert result["run_id"] == "run-1"
    assert result["task_status"] == "COMPLETED"
    assert result["stage"] == "completed"
    assert result["report_url"] == f"/api/outputs/research/reports/{research_id}.md"
    assert result["metadata"]["topic"] == "GLM5 模型调研"


def test_research_status_marks_stale_legacy_cache_failed(monkeypatch, tmp_path):
    research_id = "research_20260308_legacy"
    cache_dir = tmp_path / "data" / "user" / "research" / "cache" / research_id
    cache_dir.mkdir(parents=True, exist_ok=True)
    stale_timestamp = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    (cache_dir / "reporting_progress.json").write_text(
        json.dumps(
            {
                "research_id": research_id,
                "stage": "reporting",
                "events": [
                    {
                        "status": "writing_section",
                        "timestamp": stale_timestamp,
                        "current_section": "Conclusion",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(research_router, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(
        research_router,
        "_research_service",
        lambda: _DummyResearchService(run=None),
    )

    result = asyncio.run(research_router.research_status(research_id))

    assert result["stage"] == "failed"
    assert result["error_message"] == "stale_legacy_run"
    assert result["latest_event"]["reporting"]["current_section"] == "Conclusion"


def test_reporting_agent_write_report_resumes_existing_sections(monkeypatch):
    agent = ReportingAgent(config={"system": {"language": "zh"}, "reporting": {}})
    agent.enable_inline_citations = False
    agent.enable_citation_list = True

    persisted_sections = {
        "introduction": "## Introduction\n\n已恢复的介绍",
        "section:block_1": "## 技术特性\n\n已恢复的主体章节",
    }
    persisted_callbacks = []

    async def _unexpected_intro(*args, **kwargs):
        raise AssertionError("introduction should have been resumed")

    async def _unexpected_body(*args, **kwargs):
        raise AssertionError("section body should have been resumed")

    async def _fake_conclusion(*args, **kwargs):
        return "新的结论"

    monkeypatch.setattr(agent, "_write_introduction", _unexpected_intro)
    monkeypatch.setattr(agent, "_write_section_body", _unexpected_body)
    monkeypatch.setattr(agent, "_write_section_with_subsections", _unexpected_body)
    monkeypatch.setattr(agent, "_write_conclusion", _fake_conclusion)
    monkeypatch.setattr(agent, "_generate_references", lambda blocks: "## References\n\n[1] demo")

    outline = {
        "title": "GLM5 模型调研",
        "sections": [{"block_id": "block_1", "title": "## 技术特性"}],
        "conclusion": "## Conclusion",
    }
    blocks = [TopicBlock(block_id="block_1", sub_topic="技术特性", overview="overview")]

    report = asyncio.run(
        agent._write_report(
            "GLM5 模型调研",
            blocks,
            outline,
            resume_sections=persisted_sections,
            persist_section_callback=lambda key, content: persisted_callbacks.append(
                (key, content)
            ),
        )
    )

    assert "已恢复的介绍" in report
    assert "已恢复的主体章节" in report
    assert "新的结论" in report
    assert ("conclusion", "## Conclusion\n\n新的结论") in persisted_callbacks
    assert ("references", "## References\n\n[1] demo") in persisted_callbacks
    assert all(key not in {"introduction", "section:block_1"} for key, _ in persisted_callbacks)
