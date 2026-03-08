from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
import threading
from typing import Callable

from src.logging import get_logger

logger = get_logger("PPTTaskManager")


class PptTaskManager:
    def __init__(self, max_workers: int = 4):
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._active_tasks: dict[str, Future] = {}
        self._lock = threading.Lock()

    def submit(self, task_id: str, func: Callable, *args, **kwargs) -> None:
        future = self._executor.submit(func, task_id, *args, **kwargs)
        with self._lock:
            self._active_tasks[task_id] = future
        future.add_done_callback(lambda done: self._on_done(task_id, done))

    def is_active(self, task_id: str) -> bool:
        with self._lock:
            return task_id in self._active_tasks

    def _on_done(self, task_id: str, future: Future) -> None:
        try:
            error = future.exception()
            if error:
                logger.error(f"PPT task {task_id} failed: {error}", exc_info=error)
        except Exception as exc:
            logger.error(f"PPT task callback failed: {exc}", exc_info=True)
        finally:
            with self._lock:
                self._active_tasks.pop(task_id, None)


ppt_task_manager = PptTaskManager(max_workers=4)
