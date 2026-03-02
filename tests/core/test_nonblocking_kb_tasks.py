import asyncio
from pathlib import Path
import sys

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.api.routers import knowledge as knowledge_router
from src.api.routers import notebook as notebook_router


class _DummyTaskManager:
    def __init__(self):
        self.status_updates = []

    def generate_task_id(self, task_type: str, task_key: str) -> str:
        return f"{task_type}_{task_key}"

    def update_task_status(self, task_id: str, status: str, error: str | None = None):
        self.status_updates.append({"task_id": task_id, "status": status, "error": error})


class _DummyProgressTracker:
    def __init__(self, kb_name: str, base_dir: Path):
        self.kb_name = kb_name
        self.base_dir = base_dir
        self.task_id = None
        self.events = []

    def update(
        self,
        stage,
        message: str = "",
        current: int = 0,
        total: int = 0,
        file_name: str = "",
        error: str | None = None,
    ):
        self.events.append(
            {
                "stage": stage,
                "message": message,
                "current": current,
                "total": total,
                "file_name": file_name,
                "error": error,
            }
        )


class _DummyDocumentAdder:
    instances = []

    def __init__(self, *args, **kwargs):
        self.extract_calls = []
        self.updated_count = None
        _DummyDocumentAdder.instances.append(self)

    async def process_new_documents(self, files: list[Path]):
        return [Path("/tmp/processed_source.md")]

    def extract_numbered_items_for_new_docs(
        self, processed_files: list[Path], batch_size: int = 20
    ):
        self.extract_calls.append((processed_files, batch_size))

    def update_metadata(self, added_count: int):
        self.updated_count = added_count


def test_notebook_sources_kb_detection():
    assert knowledge_router._is_notebook_sources_kb("notebook_123abc_sources")
    assert not knowledge_router._is_notebook_sources_kb("regular_kb")


def test_upload_processing_skips_numbered_items_for_sources_kb(monkeypatch):
    task_manager = _DummyTaskManager()
    _DummyDocumentAdder.instances = []

    monkeypatch.setattr(
        knowledge_router.TaskIDManager, "get_instance", staticmethod(lambda: task_manager)
    )
    monkeypatch.setattr(knowledge_router, "ProgressTracker", _DummyProgressTracker)
    monkeypatch.setattr(knowledge_router, "DocumentAdder", _DummyDocumentAdder)

    asyncio.run(
        knowledge_router.run_upload_processing_task(
            kb_name="notebook_abc123_sources",
            base_dir="/tmp",
            api_key="test-key",
            base_url="http://test-base",
            uploaded_file_paths=["/tmp/a.md"],
        )
    )

    adder = _DummyDocumentAdder.instances[-1]
    assert adder.extract_calls == []
    assert adder.updated_count == 1


def test_upload_processing_keeps_numbered_items_for_regular_kb(monkeypatch):
    task_manager = _DummyTaskManager()
    _DummyDocumentAdder.instances = []

    monkeypatch.setattr(
        knowledge_router.TaskIDManager, "get_instance", staticmethod(lambda: task_manager)
    )
    monkeypatch.setattr(knowledge_router, "ProgressTracker", _DummyProgressTracker)
    monkeypatch.setattr(knowledge_router, "DocumentAdder", _DummyDocumentAdder)

    asyncio.run(
        knowledge_router.run_upload_processing_task(
            kb_name="regular_kb",
            base_dir="/tmp",
            api_key="test-key",
            base_url="http://test-base",
            uploaded_file_paths=["/tmp/a.md"],
        )
    )

    adder = _DummyDocumentAdder.instances[-1]
    assert len(adder.extract_calls) == 1
    assert adder.extract_calls[0][1] == 20
    assert adder.updated_count == 1


def test_sources_sync_scheduler_deduplicates_tasks(monkeypatch):
    notebook_router._ACTIVE_SOURCES_SYNC_TASKS.clear()

    async def _run():
        started = asyncio.Event()
        release = asyncio.Event()
        call_count = {"value": 0}

        async def _fake_sync(_: str):
            call_count["value"] += 1
            started.set()
            await release.wait()
            return "done"

        monkeypatch.setattr(notebook_router, "_sync_sources_kb", _fake_sync)

        first = await notebook_router._schedule_sources_kb_sync("nb-1")
        assert first is True
        await started.wait()

        second = await notebook_router._schedule_sources_kb_sync("nb-1")
        assert second is False
        assert call_count["value"] == 1

        running_task = notebook_router._ACTIVE_SOURCES_SYNC_TASKS["nb-1"]
        release.set()
        await running_task
        await asyncio.sleep(0)

        third = await notebook_router._schedule_sources_kb_sync("nb-1")
        assert third is True
        await asyncio.sleep(0)

        latest_task = notebook_router._ACTIVE_SOURCES_SYNC_TASKS.get("nb-1")
        if latest_task:
            await latest_task
        await asyncio.sleep(0)

        assert call_count["value"] == 2
        assert "nb-1" not in notebook_router._ACTIVE_SOURCES_SYNC_TASKS

    asyncio.run(_run())
