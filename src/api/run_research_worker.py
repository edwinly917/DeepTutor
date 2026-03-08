from __future__ import annotations

import asyncio
from pathlib import Path

from src.logging import get_logger
from src.services.research.research_worker import ResearchWorker
from src.services.storage import init_storage

logger = get_logger("ResearchWorkerCLI")


async def _main() -> None:
    project_root = Path(__file__).parent.parent.parent
    init_storage()
    worker = ResearchWorker(project_root)
    logger.info("Starting standalone research worker")
    await worker.run_forever()


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
