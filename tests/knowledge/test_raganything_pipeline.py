from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys

project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.agents.chat import chat_agent as chat_agent_module
from src.agents.chat.chat_agent import ChatAgent
from src.api.routers import notebook as notebook_router
from src.services.rag.pipelines.raganything import (
    RAGAnythingPipeline,
    _coerce_keyword_extraction_response,
    _wrap_keyword_extraction_for_unsupported_models,
)


def test_coerce_keyword_extraction_response_extracts_wrapped_json():
    response = _coerce_keyword_extraction_response(
        'Result: {"high_level_keywords":["交易"],"low_level_keywords":["Token","流动性"]}'
    )

    payload = json.loads(response)
    assert payload["high_level_keywords"] == ["交易"]
    assert payload["low_level_keywords"] == ["Token", "流动性"]


def test_coerce_keyword_extraction_response_returns_empty_lists_for_invalid_text():
    response = _coerce_keyword_extraction_response("not json at all")

    payload = json.loads(response)
    assert payload == {"high_level_keywords": [], "low_level_keywords": []}


def test_keyword_wrapper_falls_back_to_plain_text_json_prompt():
    calls: list[dict[str, object]] = []

    async def fake_llm_call(
        prompt: str,
        system_prompt: str | None = None,
        history_messages: list[dict[str, object]] | None = None,
        **kwargs,
    ) -> str:
        calls.append(
            {
                "prompt": prompt,
                "system_prompt": system_prompt,
                "history_messages": history_messages,
                "kwargs": kwargs,
            }
        )
        return '```json\n{"high_level_keywords":["宏观"],"low_level_keywords":["通胀"]}\n```'

    class DummyLogger:
        def info(self, *_args, **_kwargs):
            return None

    wrapped = _wrap_keyword_extraction_for_unsupported_models(
        fake_llm_call,
        model="doubao-seed-2-0-pro-260215",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        logger=DummyLogger(),
    )

    response = asyncio.run(wrapped("extract keywords", keyword_extraction=True))

    payload = json.loads(response)
    assert payload["high_level_keywords"] == ["宏观"]
    assert payload["low_level_keywords"] == ["通胀"]
    assert len(calls) == 1
    assert "keyword_extraction" not in calls[0]["kwargs"]
    assert "Return a single valid JSON object only" in str(calls[0]["prompt"])


def test_keyword_wrapper_keeps_supported_models_unchanged():
    async def fake_llm_call(*args, **kwargs):
        return "{}"

    class DummyLogger:
        def info(self, *_args, **_kwargs):
            return None

    wrapped = _wrap_keyword_extraction_for_unsupported_models(
        fake_llm_call,
        model="gpt-4o-mini",
        base_url="https://api.openai.com/v1",
        logger=DummyLogger(),
    )

    assert wrapped is fake_llm_call


def test_search_retries_without_vlm_on_invalid_prompt(monkeypatch):
    pipeline = RAGAnythingPipeline()
    calls: list[dict[str, object]] = []

    class FakeRAG:
        async def _ensure_lightrag_initialized(self):
            return None

        async def aquery(self, query: str, **kwargs):
            calls.append({"query": query, **kwargs})
            if kwargs.get("vlm_enhanced") is False:
                return "fallback answer"
            raise TypeError("expected string or bytes-like object, got 'NoneType'")

    monkeypatch.setattr(pipeline, "_get_rag_instance", lambda kb_name: FakeRAG())

    result = asyncio.run(pipeline.search(query="tokens交易包括哪些方面", kb_name="test"))

    assert result["answer"] == "fallback answer"
    assert len(calls) == 2
    assert "vlm_enhanced" not in calls[0]
    assert calls[1]["vlm_enhanced"] is False


def test_search_can_return_structured_raw_data(monkeypatch):
    pipeline = RAGAnythingPipeline()

    class FakeLightRAG:
        async def aquery_llm(self, query: str, param):
            assert query == "蓝讯通信公司情况如何"
            assert param.mode == "hybrid"
            assert param.only_need_context is True
            return {
                "status": "success",
                "data": {
                    "chunks": [
                        {
                            "content": "蓝讯通信是一家通信外包企业。",
                            "file_path": "/tmp/蓝讯通信BPO.pdf",
                            "chunk_id": "chunk-1",
                        }
                    ]
                },
                "llm_response": {
                    "content": "[Knowledge Base Context]\\n蓝讯通信是一家通信外包企业。",
                    "is_streaming": False,
                    "response_iterator": None,
                },
            }

    class FakeRAG:
        def __init__(self):
            self.lightrag = FakeLightRAG()

        async def _ensure_lightrag_initialized(self):
            return None

    monkeypatch.setattr(pipeline, "_get_rag_instance", lambda kb_name: FakeRAG())

    result = asyncio.run(
        pipeline.search(
            query="蓝讯通信公司情况如何",
            kb_name="test",
            only_need_context=True,
            return_raw_data=True,
        )
    )

    assert "蓝讯通信是一家通信外包企业" in result["answer"]
    assert result["raw_data"]["data"]["chunks"][0]["chunk_id"] == "chunk-1"


class _DummyLogger:
    def info(self, *_args, **_kwargs):
        return None

    def warning(self, *_args, **_kwargs):
        return None


def _make_chat_agent() -> ChatAgent:
    agent = ChatAgent.__new__(ChatAgent)
    agent.logger = _DummyLogger()
    return agent


def _kb_reference_source(**overrides):
    source = {
        "id": "kb-source-1",
        "type": "kb",
        "title": "蓝讯通信BPO.pdf",
        "selected": True,
        "content": "蓝讯通信是一家专注通信业务外包的企业。",
        "kb_name": "渝富notebook",
        "source_file": "蓝讯通信BPO.pdf",
        "chunk_id": "chunk-1",
        "page": 1,
        "source_key": "kb-渝富notebook|蓝讯通信BPO.pdf|1|chunk-1",
        "ref_number": 1,
    }
    source.update(overrides)
    return source


def _web_source(**overrides):
    source = {
        "id": "web-source-1",
        "type": "web",
        "title": "行业分析",
        "url": "https://example.com/report",
        "selected": True,
        "content": "这是一段足够长的网页正文内容，用于模拟可索引的来源。",
    }
    source.update(overrides)
    return source


def test_filter_materialized_sources_skips_kb_reference_sources():
    sources = [
        _kb_reference_source(),
        _web_source(),
        {
            "id": "legacy-kb",
            "type": "kb",
            "title": "Legacy KB Summary",
            "selected": True,
            "content": "legacy context",
        },
    ]

    materialized = notebook_router._filter_materialized_sources(sources)

    assert len(materialized) == 2
    assert all(source.get("kb_name") != "渝富notebook" for source in materialized)
    assert any(source["type"] == "web" for source in materialized)
    assert any(source["id"] == "legacy-kb" for source in materialized)


def test_sync_sources_kb_skips_kb_reference_only_sources(monkeypatch):
    monkeypatch.setattr(
        notebook_router.notebook_manager,
        "get_notebook",
        lambda notebook_id: {"id": notebook_id, "name": "测试笔记本"},
    )
    monkeypatch.setattr(
        notebook_router.notebook_manager,
        "list_sessions",
        lambda _notebook_id: [{"session_id": "s1", "sources": [_kb_reference_source()]}],
    )

    result = asyncio.run(notebook_router._sync_sources_kb("nb-kb-only"))

    assert result is None


def test_upsert_session_does_not_schedule_sync_for_kb_reference_only_sources(monkeypatch):
    scheduled = []

    monkeypatch.setattr(
        notebook_router.notebook_manager,
        "get_notebook",
        lambda notebook_id: {"id": notebook_id, "name": "测试笔记本"},
    )
    monkeypatch.setattr(
        notebook_router.notebook_manager,
        "upsert_session",
        lambda _notebook_id, payload: {
            "session_id": payload.get("session_id") or "session-1",
            **payload,
        },
    )
    monkeypatch.setattr(
        notebook_router.notebook_manager,
        "list_sessions",
        lambda _notebook_id: [{"session_id": "session-1", "sources": [_kb_reference_source()]}],
    )

    async def fake_schedule(_notebook_id: str):
        scheduled.append(_notebook_id)
        return True

    monkeypatch.setattr(notebook_router, "_schedule_sources_kb_sync", fake_schedule)
    monkeypatch.setattr(notebook_router, "_should_sync_sources_kb", lambda *_args, **_kwargs: True)

    request = notebook_router.SessionSnapshot(
        session_id="session-1",
        title="会话",
        messages=[],
        sources=[notebook_router.SessionSource(**_kb_reference_source())],
        created_at=1,
        updated_at=1,
    )

    result = asyncio.run(notebook_router.upsert_session("nb-kb-only", request))

    assert result["session"]["session_id"] == "session-1"
    assert scheduled == []


def test_upsert_session_schedules_sync_for_materialized_sources(monkeypatch):
    scheduled = []

    monkeypatch.setattr(
        notebook_router.notebook_manager,
        "get_notebook",
        lambda notebook_id: {"id": notebook_id, "name": "测试笔记本"},
    )
    monkeypatch.setattr(
        notebook_router.notebook_manager,
        "upsert_session",
        lambda _notebook_id, payload: {
            "session_id": payload.get("session_id") or "session-2",
            **payload,
        },
    )
    monkeypatch.setattr(
        notebook_router.notebook_manager,
        "list_sessions",
        lambda _notebook_id: [{"session_id": "session-2", "sources": [_web_source()]}],
    )

    async def fake_schedule(notebook_id: str):
        scheduled.append(notebook_id)
        return True

    monkeypatch.setattr(notebook_router, "_schedule_sources_kb_sync", fake_schedule)
    monkeypatch.setattr(notebook_router, "_should_sync_sources_kb", lambda *_args, **_kwargs: True)

    request = notebook_router.SessionSnapshot(
        session_id="session-2",
        title="会话",
        messages=[],
        sources=[notebook_router.SessionSource(**_web_source())],
        created_at=1,
        updated_at=1,
    )

    asyncio.run(notebook_router.upsert_session("nb-web", request))

    assert scheduled == ["nb-web"]


def test_retrieve_context_uses_selected_kb_snippet_without_duplicate_search(monkeypatch):
    agent = _make_chat_agent()
    calls = []

    async def fake_rag_search(query: str, kb_name: str, mode: str, **kwargs):
        calls.append({"query": query, "kb_name": kb_name, "mode": mode, **kwargs})
        if kwargs.get("return_raw_data"):
            return {
                "answer": "[Selected Context]\n蓝讯通信是一家专注通信业务外包的企业。",
                "raw_data": {
                    "data": {
                        "chunks": [
                            {
                                "content": "蓝讯通信是一家专注通信业务外包的企业。",
                                "file_path": "/tmp/蓝讯通信BPO.pdf",
                                "chunk_id": "chunk-1",
                            },
                            {
                                "content": "其他文档内容。",
                                "file_path": "/tmp/other.pdf",
                                "chunk_id": "chunk-2",
                            },
                        ]
                    }
                },
            }
        return {"answer": f"{kb_name} 的检索结果"}

    monkeypatch.setattr(chat_agent_module, "rag_search", fake_rag_search)

    context, sources, exceptions = asyncio.run(
        agent.retrieve_context(
            message="蓝讯通信公司情况如何",
            kb_name="渝富notebook",
            selected_source_refs=[_kb_reference_source()],
            enable_rag=True,
        )
    )

    assert exceptions == []
    assert len(calls) == 2
    assert calls[0]["kb_name"] == "渝富notebook"
    assert calls[0]["return_raw_data"] is True
    assert calls[0]["only_need_context"] is True
    assert calls[1]["kb_name"] == "渝富notebook"
    assert "[Selected Knowledge Base Reference]" in context
    assert "[Selected Knowledge Base Exact Match]" in context
    assert "蓝讯通信是一家专注通信业务外包的企业。" in context
    assert "[Knowledge Base: 渝富notebook]" in context
    assert any(source.get("chunk_id") == "chunk-1" for source in sources["rag"])


def test_retrieve_context_queries_original_referenced_kb_when_needed(monkeypatch):
    agent = _make_chat_agent()
    calls = []

    async def fake_rag_search(query: str, kb_name: str, mode: str, **kwargs):
        calls.append({"query": query, "kb_name": kb_name, "mode": mode, **kwargs})
        if kwargs.get("return_raw_data"):
            return {"answer": "", "raw_data": {"data": {"chunks": []}}}
        return {"answer": f"{kb_name} 的补充检索结果"}

    monkeypatch.setattr(chat_agent_module, "rag_search", fake_rag_search)

    context, sources, exceptions = asyncio.run(
        agent.retrieve_context(
            message="蓝讯通信公司情况如何",
            enable_rag=False,
            selected_source_refs=[_kb_reference_source(content="", ref_number=None)],
        )
    )

    assert exceptions == []
    assert len(calls) == 2
    assert calls[0]["kb_name"] == "渝富notebook"
    assert calls[0]["return_raw_data"] is True
    assert calls[1]["kb_name"] == "渝富notebook"
    assert "[Referenced Knowledge Base: 渝富notebook]" in context
    assert sources["rag"][0]["kb_name"] == "渝富notebook"


def test_retrieve_context_prefers_precise_referenced_kb_chunks(monkeypatch):
    agent = _make_chat_agent()
    calls = []

    async def fake_rag_search(query: str, kb_name: str, mode: str, **kwargs):
        calls.append({"query": query, "kb_name": kb_name, "mode": mode, **kwargs})
        if kwargs.get("return_raw_data"):
            return {
                "answer": "[Selected Context]\n蓝讯通信是一家通信外包企业。",
                "raw_data": {
                    "data": {
                        "chunks": [
                            {
                                "content": "蓝讯通信是一家通信外包企业。",
                                "file_path": "/tmp/蓝讯通信BPO.pdf",
                                "chunk_id": "chunk-1",
                            },
                            {
                                "content": "不相关的其他公司内容。",
                                "file_path": "/tmp/other.pdf",
                                "chunk_id": "chunk-9",
                            },
                        ]
                    }
                },
            }
        return {"answer": f"{kb_name} 的泛化检索结果"}

    monkeypatch.setattr(chat_agent_module, "rag_search", fake_rag_search)

    context, sources, exceptions = asyncio.run(
        agent.retrieve_context(
            message="蓝讯通信公司情况如何",
            enable_rag=False,
            selected_source_refs=[_kb_reference_source(content="")],
        )
    )

    assert exceptions == []
    assert len(calls) == 1
    assert calls[0]["return_raw_data"] is True
    assert "[Selected Knowledge Base Exact Match]" in context
    assert "蓝讯通信是一家通信外包企业。" in context
    assert "[Referenced Knowledge Base:" not in context
    assert any(source.get("chunk_id") == "chunk-1" for source in sources["rag"])
