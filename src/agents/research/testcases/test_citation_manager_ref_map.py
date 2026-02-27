from pathlib import Path
import sys

project_root = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(project_root))

from src.agents.research.utils.citation_manager import CitationManager


def test_build_ref_number_map_skips_plan_and_non_citable(tmp_path):
    manager = CitationManager("research_test", cache_dir=tmp_path)
    manager._citations = {
        "PLAN-01": {
            "citation_id": "PLAN-01",
            "tool_type": "rag_hybrid",
            "citable": False,
            "source_count": 0,
        },
        "CIT-1-01": {
            "citation_id": "CIT-1-01",
            "tool_type": "rag_hybrid",
            "citable": False,
            "source_count": 0,
        },
        "CIT-1-02": {
            "citation_id": "CIT-1-02",
            "tool_type": "web_search",
            "citable": True,
            "source_count": 1,
            "web_sources": [{"title": "A", "url": "https://a.com"}],
        },
        "CIT-1-03": {
            "citation_id": "CIT-1-03",
            "tool_type": "web_search",
            "citable": True,
            "source_count": 1,
            "web_sources": [{"title": "B", "url": "https://b.com"}],
        },
    }

    ref_map = manager.build_ref_number_map()
    assert ref_map == {
        "CIT-1-02": 1,
        "CIT-1-03": 2,
    }


def test_build_ref_number_map_backward_compatible_filters_empty_source(tmp_path):
    manager = CitationManager("research_test", cache_dir=tmp_path)
    manager._citations = {
        "CIT-1-01": {
            "citation_id": "CIT-1-01",
            "tool_type": "rag_hybrid",
            "sources": [],
        },
        "CIT-1-02": {
            "citation_id": "CIT-1-02",
            "tool_type": "web_search",
            "web_sources": [{"title": "A", "url": "https://a.com"}],
        },
    }

    ref_map = manager.build_ref_number_map()
    assert ref_map == {"CIT-1-02": 1}


def test_build_ref_number_map_handles_paper_entries(tmp_path):
    manager = CitationManager("research_test", cache_dir=tmp_path)
    manager._citations = {
        "CIT-2-01": {
            "citation_id": "CIT-2-01",
            "tool_type": "paper_search",
            "citable": True,
            "source_count": 2,
            "papers": [
                {"title": "Paper A", "authors": "Alice"},
                {"title": "Paper B", "authors": "Bob"},
            ],
        }
    }

    ref_map = manager.build_ref_number_map()
    assert ref_map["CIT-2-01"] == 1
    assert ref_map["CIT-2-01-1"] == 1
    assert ref_map["CIT-2-01-2"] == 2
