from __future__ import annotations

import asyncio
import contextlib
import os
from pathlib import Path
import time
from typing import Any

import psutil

from src.logging import get_logger

logger = get_logger("MineruTimeout")

DEFAULT_MINERU_TIMEOUT_SECONDS = 600.0
DEFAULT_MINERU_VLM_TIMEOUT_SECONDS = 7200.0
MINERU_VLM_FILE_SUFFIXES = {
    ".pdf",
    ".png",
    ".jpeg",
    ".jpg",
    ".bmp",
    ".tiff",
    ".tif",
    ".gif",
    ".webp",
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".xls",
    ".xlsx",
    ".html",
    ".htm",
    ".xhtml",
}


class MineruProcessTimeout(asyncio.TimeoutError):
    def __init__(
        self,
        *,
        file_path: Path,
        timeout_seconds: float,
        elapsed_seconds: float,
        terminated_pids: list[int],
    ) -> None:
        self.file_path = Path(file_path)
        self.timeout_seconds = timeout_seconds
        self.elapsed_seconds = elapsed_seconds
        self.terminated_pids = terminated_pids
        pid_text = ", ".join(str(pid) for pid in terminated_pids) if terminated_pids else "none"
        super().__init__(
            f"MinerU processing timeout for {self.file_path.name} after "
            f"{elapsed_seconds:.1f}s (limit: {timeout_seconds:.1f}s); "
            f"terminated pids: {pid_text}"
        )


def _get_env_float(name: str, default: float) -> float:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    try:
        value = float(raw_value)
    except ValueError:
        logger.warning(f"Invalid float env {name}={raw_value!r}, using default {default}")
        return default
    return value if value > 0 else default


def get_mineru_processing_timeout_seconds(file_path: str | Path) -> float:
    path = Path(file_path)
    if path.suffix.lower() in MINERU_VLM_FILE_SUFFIXES:
        return _get_env_float(
            "KNOWLEDGE_MINERU_VLM_TIMEOUT_SECONDS",
            DEFAULT_MINERU_VLM_TIMEOUT_SECONDS,
        )
    return _get_env_float(
        "KNOWLEDGE_MINERU_TIMEOUT_SECONDS",
        DEFAULT_MINERU_TIMEOUT_SECONDS,
    )


def _looks_like_mineru_process(process: psutil.Process) -> bool:
    with contextlib.suppress(psutil.Error):
        cmdline = process.cmdline()
        if not cmdline:
            return False
        joined = " ".join(cmdline).lower()
        first = Path(cmdline[0]).name.lower()
        return "mineru" in first or "mineru" in joined
    return False


def _matches_document_scope(
    process: psutil.Process,
    *,
    file_path: str,
    output_dir: str,
) -> bool:
    with contextlib.suppress(psutil.Error):
        cmdline = process.cmdline()
        if not cmdline:
            return False
        joined = " ".join(cmdline)
        return file_path in joined or output_dir in joined
    return False


def terminate_mineru_processes(*, file_path: str | Path, output_dir: str | Path) -> list[int]:
    file_path_str = str(Path(file_path))
    output_dir_str = str(Path(output_dir))

    matched: list[psutil.Process] = []
    for process in psutil.process_iter(["pid", "name", "cmdline"]):
        if not _looks_like_mineru_process(process):
            continue
        if _matches_document_scope(
            process,
            file_path=file_path_str,
            output_dir=output_dir_str,
        ):
            matched.append(process)

    if not matched:
        return []

    victims: list[psutil.Process] = []
    seen: set[int] = set()
    for process in matched:
        with contextlib.suppress(psutil.Error):
            children = process.children(recursive=True)
        for candidate in [*children, process]:
            if candidate.pid in seen:
                continue
            seen.add(candidate.pid)
            victims.append(candidate)

    for process in victims:
        with contextlib.suppress(psutil.Error):
            process.terminate()

    _, alive = psutil.wait_procs(victims, timeout=3)

    for process in alive:
        with contextlib.suppress(psutil.Error):
            process.kill()

    if alive:
        psutil.wait_procs(alive, timeout=2)

    terminated_pids = sorted(seen)
    if terminated_pids:
        logger.warning(
            f"Terminated MinerU process tree for {Path(file_path_str).name}: {terminated_pids}"
        )
    return terminated_pids


async def process_document_with_timeout(
    *,
    rag: Any,
    file_path: str | Path,
    output_dir: str | Path,
    parse_method: str = "auto",
    timeout_seconds: float | None = None,
    logger_instance=None,
    **kwargs,
) -> float:
    active_logger = logger_instance or logger
    timeout_seconds = timeout_seconds or get_mineru_processing_timeout_seconds(file_path)
    start_time = time.monotonic()

    active_logger.info(
        f"  → MinerU timeout for {Path(file_path).name} set to {timeout_seconds:.1f}s"
    )

    try:
        await asyncio.wait_for(
            rag.process_document_complete(
                file_path=str(file_path),
                output_dir=str(output_dir),
                parse_method=parse_method,
                **kwargs,
            ),
            timeout=timeout_seconds,
        )
        return time.monotonic() - start_time
    except asyncio.TimeoutError as exc:
        elapsed_seconds = time.monotonic() - start_time
        terminated_pids = terminate_mineru_processes(
            file_path=file_path,
            output_dir=output_dir,
        )
        raise MineruProcessTimeout(
            file_path=Path(file_path),
            timeout_seconds=timeout_seconds,
            elapsed_seconds=elapsed_seconds,
            terminated_pids=terminated_pids,
        ) from exc
