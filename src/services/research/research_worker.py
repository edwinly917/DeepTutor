from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import signal
from typing import Any
import uuid

from src.agents.research.data_structures import DynamicTopicQueue, TopicStatus
from src.agents.research.research_pipeline import ResearchPipeline
from src.api.utils.history import ActivityType, history_manager
from src.logging import get_logger
from src.services.llm import get_llm_config
from src.services.storage import research_store

from .research_run_service import get_research_run_service

logger = get_logger("ResearchWorker")


class ResearchRunCancelled(RuntimeError):
    pass


@dataclass
class WorkerConfig:
    max_concurrency: int = 1
    poll_interval_ms: int = 1000
    lease_ttl_seconds: int = 90
    heartbeat_interval_seconds: int = 15
    stale_session_clear_seconds: int = 120


class ResearchWorker:
    def __init__(self, project_root: Path, *, worker_id: str | None = None):
        self.project_root = project_root
        self.worker_id = worker_id or f"research-worker-{uuid.uuid4().hex[:8]}"
        self.service = get_research_run_service(project_root)
        self.config = self._load_worker_config()
        self._shutdown = asyncio.Event()

    def _load_worker_config(self) -> WorkerConfig:
        from src.services.config import load_config_with_main

        config = load_config_with_main("research_config.yaml", self.project_root)
        worker_cfg = config.get("research", {}).get("worker", {})
        return WorkerConfig(
            max_concurrency=max(1, int(worker_cfg.get("max_concurrency", 1))),
            poll_interval_ms=max(200, int(worker_cfg.get("poll_interval_ms", 1000))),
            lease_ttl_seconds=max(30, int(worker_cfg.get("lease_ttl_seconds", 90))),
            heartbeat_interval_seconds=max(
                5, int(worker_cfg.get("heartbeat_interval_seconds", 15))
            ),
            stale_session_clear_seconds=max(
                60, int(worker_cfg.get("stale_session_clear_seconds", 120))
            ),
        )

    async def run_forever(self) -> None:
        self._install_signal_handlers()
        await self._mark_stale_running_runs_failed()
        logger.info(f"Research worker started: {self.worker_id}")
        while not self._shutdown.is_set():
            run = research_store.claim_next_run(
                self.worker_id, lease_ttl_seconds=self.config.lease_ttl_seconds
            )
            if not run:
                await asyncio.sleep(self.config.poll_interval_ms / 1000)
                continue
            try:
                await self._execute_run(run)
            except Exception as exc:
                logger.error(f"Run {run['id']} execution failed: {exc}", exc_info=True)
                self.service.mark_failed(run["id"], str(exc))
            finally:
                research_store.release_lease(run["id"], self.worker_id)

    async def _execute_run(self, run: dict[str, Any]) -> None:
        heartbeat_task = asyncio.create_task(self._heartbeat_loop(run["id"]))
        try:
            await self._run_phases(run)
        finally:
            heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat_task

    async def _heartbeat_loop(self, run_id: str) -> None:
        while not self._shutdown.is_set():
            await asyncio.sleep(self.config.heartbeat_interval_seconds)
            renewed = research_store.renew_lease(
                run_id,
                self.worker_id,
                lease_ttl_seconds=self.config.lease_ttl_seconds,
            )
            if not renewed:
                return

    async def _run_phases(self, run: dict[str, Any]) -> None:
        pipeline = self._build_pipeline(run)
        self._restore_pipeline_state(pipeline, run)
        checkpoint = dict(run.get("checkpoint") or {})
        topic = run["topic"]
        optimized_topic = checkpoint.get("optimized_topic") or topic

        if run["status"] == "CANCEL_REQUESTED":
            self.service.mark_cancelled(run["id"])
            return

        if not checkpoint.get("planning_completed"):
            optimized_topic = await pipeline._phase1_planning(topic)
            queue_stats = pipeline.queue.get_statistics()
            self.service.mark_phase_checkpoint(
                run["id"],
                phase="PLANNING",
                checkpoint_patch={
                    "optimized_topic": optimized_topic,
                    "planning_completed": True,
                    "topic": topic,
                },
                progress={
                    "current": 0,
                    "total": int(queue_stats.get("total_blocks") or 0),
                    "message": "planning completed",
                    "stage": "planning",
                },
            )
            checkpoint = dict((research_store.get_run(run["id"]) or {}).get("checkpoint") or {})

        optimized_topic = checkpoint.get("optimized_topic") or optimized_topic
        pipeline.optimized_topic = optimized_topic
        pipeline.agents["manager"].set_primary_topic(optimized_topic)

        if run["status"] == "CANCEL_REQUESTED":
            self.service.mark_cancelled(run["id"])
            return

        if not checkpoint.get("researching_completed"):
            await pipeline._phase2_researching()
            queue_stats = pipeline.queue.get_statistics()
            self.service.mark_phase_checkpoint(
                run["id"],
                phase="RESEARCHING",
                checkpoint_patch={
                    "optimized_topic": optimized_topic,
                    "researching_completed": True,
                },
                progress={
                    "current": int(queue_stats.get("completed") or 0),
                    "total": int(queue_stats.get("total_blocks") or 0),
                    "message": "researching completed",
                    "stage": "researching",
                },
            )
            checkpoint = dict((research_store.get_run(run["id"]) or {}).get("checkpoint") or {})

        if run["status"] == "CANCEL_REQUESTED":
            self.service.mark_cancelled(run["id"])
            return

        resume_outline = self._load_resume_outline(run)
        resume_sections = self._load_resume_sections(run)
        report_result = await pipeline._phase3_reporting(
            optimized_topic,
            resume_outline=resume_outline,
            resume_sections=resume_sections,
            persist_outline_callback=lambda outline: self._persist_outline(
                run["id"], run["research_id"], outline
            ),
            persist_section_callback=lambda key, content: self._persist_section(
                run["id"], run["research_id"], key, content
            ),
        )
        self.service.mark_phase_checkpoint(
            run["id"],
            phase="REPORTING",
            checkpoint_patch={"reporting_completed": True, "optimized_topic": optimized_topic},
            progress={
                "current": int(report_result.get("sections") or 0),
                "total": int(report_result.get("sections") or 0),
                "message": "reporting completed",
                "stage": "reporting",
            },
        )
        saved = self._save_final_outputs(run, pipeline, topic, optimized_topic, report_result)
        self.service.mark_completed(
            run["id"],
            report_path=saved["report_path"],
            metadata_path=saved["metadata_path"],
            report_content=report_result["report"],
            metadata=saved["metadata"],
        )
        history_manager.add_entry(
            activity_type=ActivityType.RESEARCH,
            title=topic,
            content={
                "topic": topic,
                "report": report_result["report"],
                "kb_name": run.get("kb_name"),
            },
            summary=f"Research ID: {run['research_id']}",
            notebook_id=run.get("notebook_id"),
        )

    def _build_pipeline(self, run: dict[str, Any]) -> ResearchPipeline:
        llm_config = get_llm_config()

        def progress_callback(event: dict[str, Any]) -> None:
            payload = dict(event)
            payload.setdefault("research_id", run["research_id"])
            payload.setdefault("run_id", run["id"])
            self.service.append_event(
                run["id"], payload, stage=str(payload.get("stage") or "").upper() or None
            )

        return ResearchPipeline(
            config=run["config_snapshot"],
            api_key=llm_config.api_key,
            base_url=llm_config.base_url,
            kb_name=run.get("kb_name"),
            progress_callback=progress_callback,
            research_id=run["research_id"],
        )

    def _restore_pipeline_state(self, pipeline: ResearchPipeline, run: dict[str, Any]) -> None:
        checkpoint = dict(run.get("checkpoint") or {})
        pipeline.input_topic = run["topic"]
        pipeline.optimized_topic = checkpoint.get("optimized_topic")
        paths = self.service.research_paths(run["research_id"])
        queue_progress_file = paths["queue_progress_file"]
        queue_file = paths["queue_file"]
        source_queue_file = queue_progress_file if queue_progress_file.exists() else queue_file
        if source_queue_file.exists():
            queue = DynamicTopicQueue.load_from_json(str(source_queue_file))
            queue.state_file = str(queue_progress_file)
            for block in queue.blocks:
                if block.status == TopicStatus.RESEARCHING:
                    block.status = TopicStatus.PENDING
                    block.updated_at = datetime.now().isoformat()
            queue.save_to_json(str(queue_progress_file))
            pipeline.queue = queue
            pipeline.agents["manager"].set_queue(queue)
        if pipeline.optimized_topic:
            pipeline.agents["manager"].set_primary_topic(pipeline.optimized_topic)

    def _persist_outline(self, run_id: str, research_id: str, outline: dict[str, Any]) -> None:
        paths = self.service.research_paths(research_id)
        paths["cache_dir"].mkdir(parents=True, exist_ok=True)
        with open(paths["outline_file"], "w", encoding="utf-8") as handle:
            json.dump(outline, handle, ensure_ascii=False, indent=2)
        self.service.mark_phase_checkpoint(
            run_id,
            phase="REPORTING",
            checkpoint_patch={"outline_saved": True},
        )

    def _persist_section(self, run_id: str, research_id: str, key: str, content: str) -> None:
        paths = self.service.research_paths(research_id)
        paths["sections_dir"].mkdir(parents=True, exist_ok=True)
        safe_name = key.replace(":", "__") + ".md"
        section_path = paths["sections_dir"] / safe_name
        section_path.write_text(content, encoding="utf-8")
        run = research_store.get_run(run_id) or {}
        checkpoint = dict(run.get("checkpoint") or {})
        completed = list(checkpoint.get("completed_section_keys") or [])
        if key not in completed:
            completed.append(key)
        self.service.mark_phase_checkpoint(
            run_id,
            phase="REPORTING",
            checkpoint_patch={"completed_section_keys": completed},
        )
        current = research_store.get_run(run_id)
        if current and current.get("status") == "CANCEL_REQUESTED":
            raise ResearchRunCancelled("研究任务已取消")

    def _load_resume_outline(self, run: dict[str, Any]) -> dict[str, Any] | None:
        paths = self.service.research_paths(run["research_id"])
        if not paths["outline_file"].exists():
            return None
        try:
            return json.loads(paths["outline_file"].read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning(f"Failed to load outline checkpoint for {run['id']}: {exc}")
            return None

    def _load_resume_sections(self, run: dict[str, Any]) -> dict[str, str]:
        paths = self.service.research_paths(run["research_id"])
        if not paths["sections_dir"].exists():
            return {}
        sections: dict[str, str] = {}
        for file_path in sorted(paths["sections_dir"].glob("*.md")):
            key = file_path.stem.replace("__", ":")
            try:
                sections[key] = file_path.read_text(encoding="utf-8")
            except Exception as exc:
                logger.warning(f"Failed to load section checkpoint {file_path}: {exc}")
        return sections

    def _save_final_outputs(
        self,
        run: dict[str, Any],
        pipeline: ResearchPipeline,
        topic: str,
        optimized_topic: str,
        report_result: dict[str, Any],
    ) -> dict[str, Any]:
        paths = self.service.research_paths(run["research_id"])
        paths["reports_dir"].mkdir(parents=True, exist_ok=True)
        paths["cache_dir"].mkdir(parents=True, exist_ok=True)
        paths["report_file"].write_text(report_result["report"], encoding="utf-8")
        pipeline.queue.save_to_json(str(paths["queue_file"]))
        if "outline" in report_result:
            with open(paths["outline_file"], "w", encoding="utf-8") as handle:
                json.dump(report_result["outline"], handle, ensure_ascii=False, indent=2)
        sources = report_result.get("sources", {"web": [], "rag": []})
        metadata = {
            "research_id": run["research_id"],
            "topic": topic,
            "optimized_topic": optimized_topic,
            "statistics": pipeline.queue.get_statistics(),
            "report_word_count": report_result["word_count"],
            "web_sources": sources.get("web", []),
            "rag_sources": sources.get("rag", []),
            "source_catalog": report_result.get("source_catalog", []),
            "completed_at": datetime.now().isoformat(),
        }
        with open(paths["metadata_file"], "w", encoding="utf-8") as handle:
            json.dump(metadata, handle, ensure_ascii=False, indent=2)
        return {
            "report_path": str(paths["report_file"]),
            "metadata_path": str(paths["metadata_file"]),
            "metadata": metadata,
        }

    async def _mark_stale_running_runs_failed(self) -> None:
        stale_runs = research_store.list_terminal_stale_runs(
            older_than_seconds=self.config.stale_session_clear_seconds
        )
        for run in stale_runs:
            logger.warning(f"Mark stale legacy running research as failed: {run['id']}")
            self.service.mark_failed(run["id"], "research worker restarted before completion")

    def shutdown(self) -> None:
        self._shutdown.set()

    def _install_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(sig, self.shutdown)
