import asyncio
from pathlib import Path
import sys

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.api.routers import knowledge as knowledge_router
from src.api.routers import notebook as notebook_router
from src.services.config import BananaPptImageConfig
from src.services.export import banana_ppt_service as banana_module
from src.services.export.banana_ppt_service import BananaPptService


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


class _DummyLLMConfig:
    model = "mock-llm"
    api_key = ""
    base_url = "https://example.com"
    binding = "openai"


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


def test_outline_prompt_no_longer_forces_abstract_images(monkeypatch, tmp_path):
    service = BananaPptService(tmp_path)
    service.config.outline.model = "mock-outline-model"

    captured = {}

    async def _fake_complete(**kwargs):
        captured["prompt"] = kwargs["prompt"]
        return (
            '{"title":"Demo","subtitle":"","themeColor":"#3b82f6","accentColor":"#f59e0b",'
            '"slides":[{"title":"Market Outlook","points":["Demand rises"],'
            '"layout":"TOP_IMAGE","imagePrompt":"industrial park at sunrise"}]}'
        )

    monkeypatch.setattr(banana_module, "llm_complete", _fake_complete)
    monkeypatch.setattr(banana_module, "get_llm_config", lambda: _DummyLLMConfig())
    monkeypatch.setattr(banana_module, "get_token_limit_kwargs", lambda model, max_tokens: {})

    result = asyncio.run(service.generate_outline("source content", style_prompt="clean corporate"))
    prompt = captured["prompt"]

    assert result["slides"][0]["imagePrompt"] == "industrial park at sunrise"
    assert "ONLY abstract visual metaphors" not in prompt
    assert "abstract upward arrows symbolizing growth" not in prompt
    assert "imagePrompt must directly match the slide title and key points" in prompt


def test_build_image_prompt_includes_slide_context(tmp_path):
    service = BananaPptService(tmp_path)

    prompt = service._build_image_generation_prompt(
        prompt="automated warehouse with robotics",
        slide_title="Smart Logistics",
        slide_points=["Automation reduces error rate", "Faster fulfillment"],
        layout="SPLIT_IMAGE_RIGHT",
        deck_title="2026 Operations Plan",
        style_prompt="clean and modern",
        simplified=False,
    )

    assert "Slide title: Smart Logistics" in prompt
    assert "- Automation reduces error rate" in prompt
    assert "Target layout: SPLIT_IMAGE_RIGHT" in prompt
    assert "Visual style guidance: clean and modern" in prompt
    assert "Image brief: automated warehouse with robotics" in prompt
    assert "ONLY abstract visual metaphors" not in prompt


def test_hash_prompt_uses_new_versioned_strategy(tmp_path):
    service = BananaPptService(tmp_path)
    cfg = BananaPptImageConfig(
        model="gemini-2.5-flash-image",
        api_key="",
        base_url="https://example.com",
        binding="gemini",
        aspect_ratio="16:9",
    )
    prompt = "clean energy landscape"

    new_hash = service._hash_prompt(prompt, cfg)

    old_hasher = banana_module.hashlib.sha256()
    old_hasher.update(cfg.model.encode("utf-8"))
    old_hasher.update(b"|")
    old_hasher.update(cfg.aspect_ratio.encode("utf-8"))
    old_hasher.update(b"|")
    old_hasher.update(prompt.encode("utf-8"))
    old_hash = old_hasher.hexdigest()

    assert new_hash != old_hash
    assert new_hash == service._hash_prompt(prompt, cfg)


def test_generate_image_supports_legacy_prompt_only_call(monkeypatch, tmp_path):
    service = BananaPptService(tmp_path)
    service.config.image.model = "mock-image-model"
    service.config.image.base_url = "https://example.com"
    service.config.image.binding = "gemini"

    captured = {}

    def _fake_generate_with_cache(effective_prompt, cfg):
        captured["prompt"] = effective_prompt
        return "data:image/png;base64,abc123"

    monkeypatch.setattr(service, "_generate_image_with_cache", _fake_generate_with_cache)

    image_data = asyncio.run(service.generate_image("solar panels on a hillside"))

    assert image_data == "data:image/png;base64,abc123"
    assert "Image brief: solar panels on a hillside" in captured["prompt"]


def test_generate_image_retries_with_simplified_prompt(monkeypatch, tmp_path):
    service = BananaPptService(tmp_path)
    service.config.image.model = "mock-image-model"
    service.config.image.base_url = "https://example.com"
    service.config.image.binding = "gemini"

    calls = []

    def _fake_generate_with_cache(effective_prompt, cfg):
        calls.append(effective_prompt)
        if len(calls) == 1:
            return None
        return "data:image/png;base64,retry-ok"

    monkeypatch.setattr(service, "_generate_image_with_cache", _fake_generate_with_cache)

    image_data = asyncio.run(
        service.generate_image(
            prompt="urban mobility ecosystem",
            slide_title="Mobility Transformation",
            slide_points=[
                "E-bikes and micro-transit expand access",
                "Lower congestion in urban core",
            ],
            layout="TOP_IMAGE",
            deck_title="City Strategy",
            style_prompt="editorial photography style",
        )
    )

    assert image_data == "data:image/png;base64,retry-ok"
    assert len(calls) == 2
    assert "Slide key points:" in calls[0]
    assert "Slide key points:" not in calls[1]
