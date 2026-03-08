from __future__ import annotations

from datetime import datetime
import hashlib
from pathlib import Path
from typing import Any

from src.services.config import load_config_with_main


def load_research_root_config(project_root: Path) -> dict[str, Any]:
    return load_config_with_main("research_config.yaml", project_root)


def build_dedupe_key(
    *, notebook_id: str | None, session_id: str | None, kb_name: str | None, topic: str
) -> str:
    normalized_topic = " ".join((topic or "").lower().split())
    topic_hash = hashlib.sha1(normalized_topic.encode("utf-8")).hexdigest()[:16]
    if notebook_id and session_id:
        return f"nb:{notebook_id}:session:{session_id}"
    if notebook_id:
        return f"nb:{notebook_id}:topic:{topic_hash}"
    return f"kb:{kb_name or 'default'}:topic:{topic_hash}"


def generate_research_id(now: datetime | None = None) -> str:
    current = now or datetime.now()
    return f"research_{current.strftime('%Y%m%d_%H%M%S')}_{hashlib.sha1(str(current.timestamp()).encode()).hexdigest()[:6]}"


def build_effective_research_config(
    *,
    project_root: Path,
    kb_name: str | None,
    plan_mode: str,
    enabled_tools: list[str] | None,
    skip_rephrase: bool,
    preset: str | None = None,
    research_mode: str | None = None,
) -> dict[str, Any]:
    config = load_research_root_config(project_root)
    research_config = config.get("research", {})

    if "planning" not in config:
        config["planning"] = research_config.get("planning", {}).copy()
    else:
        default_planning = research_config.get("planning", {})
        for key, value in default_planning.items():
            if key not in config["planning"]:
                config["planning"][key] = value if not isinstance(value, dict) else value.copy()
            elif isinstance(value, dict) and isinstance(config["planning"][key], dict):
                for nested_key, nested_value in value.items():
                    if nested_key not in config["planning"][key]:
                        config["planning"][key][nested_key] = nested_value

    if "decompose" not in config["planning"]:
        config["planning"]["decompose"] = {}
    if "rephrase" not in config["planning"]:
        config["planning"]["rephrase"] = {}

    if "researching" not in config:
        config["researching"] = research_config.get("researching", {}).copy()
    else:
        default_researching = research_config.get("researching", {})
        for key, value in default_researching.items():
            if key not in config["researching"]:
                config["researching"][key] = value

    if "reporting" not in config:
        config["reporting"] = research_config.get("reporting", {}).copy()
    else:
        default_reporting = research_config.get("reporting", {})
        for key, value in default_reporting.items():
            if key not in config["reporting"]:
                config["reporting"][key] = value

    plan_mode_config = {
        "quick": {
            "planning": {"decompose": {"initial_subtopics": 2, "mode": "manual"}},
            "researching": {"max_iterations": 2, "iteration_mode": "fixed"},
            "reporting": {"report_type": "summary"},
        },
        "medium": {
            "planning": {"decompose": {"initial_subtopics": 5, "mode": "manual"}},
            "researching": {"max_iterations": 4, "iteration_mode": "fixed"},
        },
        "deep": {
            "planning": {"decompose": {"initial_subtopics": 8, "mode": "manual"}},
            "researching": {"max_iterations": 7, "iteration_mode": "fixed"},
        },
        "auto": {
            "planning": {"decompose": {"mode": "auto", "auto_max_subtopics": 8}},
            "researching": {"max_iterations": 6, "iteration_mode": "flexible"},
        },
    }
    if plan_mode in plan_mode_config:
        mode_cfg = plan_mode_config[plan_mode]
        if "planning" in mode_cfg:
            for key, value in mode_cfg["planning"].items():
                if key not in config["planning"]:
                    config["planning"][key] = {}
                config["planning"][key].update(value)
        if "researching" in mode_cfg:
            config["researching"].update(mode_cfg["researching"])
        if "reporting" in mode_cfg:
            config["reporting"].update(mode_cfg["reporting"])

    if preset and "presets" in config and preset in config["presets"]:
        preset_config = config["presets"][preset]
        for key, value in preset_config.items():
            if key in config and isinstance(value, dict):
                config[key].update(value)

    tools = list(dict.fromkeys((enabled_tools or ["RAG"]) + ["Web"]))
    config["researching"]["enable_rag_naive"] = "RAG" in tools
    config["researching"]["enable_rag_hybrid"] = "RAG" in tools
    config["researching"]["enable_query_item"] = "RAG" in tools
    config["researching"]["enable_paper_search"] = "Paper" in tools
    config["researching"]["enable_web_search"] = "Web" in tools
    config["researching"]["enable_run_code"] = True
    config["researching"]["enabled_tools"] = tools

    if research_mode:
        config["researching"]["research_mode"] = research_mode
    if skip_rephrase:
        config["planning"]["rephrase"]["enabled"] = False

    output_base = project_root / "data" / "user" / "research"
    if "system" not in config:
        config["system"] = {}
    config["system"]["output_base_dir"] = str(output_base / "cache")
    config["system"]["reports_dir"] = str(output_base / "reports")
    if kb_name is not None:
        config.setdefault("rag", {})["kb_name"] = kb_name
    return config


def build_research_paths(project_root: Path, research_id: str) -> dict[str, Path]:
    base_dir = project_root / "data" / "user" / "research"
    cache_dir = base_dir / "cache" / research_id
    reports_dir = base_dir / "reports"
    sections_dir = cache_dir / "report_sections"
    return {
        "base_dir": base_dir,
        "cache_dir": cache_dir,
        "reports_dir": reports_dir,
        "sections_dir": sections_dir,
        "report_file": reports_dir / f"{research_id}.md",
        "metadata_file": reports_dir / f"{research_id}_metadata.json",
        "outline_file": cache_dir / "outline.json",
        "queue_file": cache_dir / "queue.json",
        "queue_progress_file": cache_dir / "queue_progress.json",
        "reporting_progress_file": cache_dir / "reporting_progress.json",
        "planning_progress_file": cache_dir / "planning_progress.json",
        "researching_progress_file": cache_dir / "researching_progress.json",
        "reporting_checkpoint_file": cache_dir / "reporting_checkpoint.json",
    }
