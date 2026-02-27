import json
from pathlib import Path
import sys

project_root = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(project_root))

from src.agents.research.utils.source_quality import extract_source_count, is_uninformative_result


def test_extract_source_count_from_query_item_items():
    payload = {
        "status": "success",
        "count": 2,
        "items": [{"identifier": "1.1"}, {"identifier": "1.2"}],
    }
    raw = json.dumps(payload, ensure_ascii=False)

    assert extract_source_count("query_item", raw) == 2


def test_is_uninformative_result_detects_no_info_message():
    payload = {"answer": "我没有足够的信息来回答该问题。", "sources": []}
    raw = json.dumps(payload, ensure_ascii=False)

    assert is_uninformative_result("rag_hybrid", raw, payload["answer"]) is True


def test_is_uninformative_result_false_when_sources_exist():
    payload = {"answer": "已找到相关信息", "sources": [{"title": "A", "content_preview": "x"}]}
    raw = json.dumps(payload, ensure_ascii=False)

    assert is_uninformative_result("rag_hybrid", raw, payload["answer"]) is False
