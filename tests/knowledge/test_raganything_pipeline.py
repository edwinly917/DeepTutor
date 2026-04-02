from __future__ import annotations

import asyncio
import json

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
