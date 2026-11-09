"""Воркер процессов Temporal: берёт задачи из очереди и выполняет шаги.

Запуск: make worker. Шаги с базой и диском исполняются в пуле потоков (activity_executor):
движок не берёт такие шаги без пула, и один разбор документа не встаёт поперёк остальных.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from temporalio.worker import Worker

from app.core.config import get_settings
from app.core.db import init_pool
from app.core.logging import setup_logging
from app.temporal.activities import ACTIVITIES
from app.temporal.client import get_client
from app.temporal.workflows import WORKFLOWS

logger = logging.getLogger(__name__)


async def main() -> None:
    setup_logging()
    settings = get_settings()
    init_pool()  # пул соединений — ресурс уровня процесса воркера
    client = await get_client()
    with ThreadPoolExecutor(max_workers=settings.temporal_activity_workers) as executor:
        worker = Worker(
            client,
            task_queue=settings.temporal_task_queue,
            workflows=WORKFLOWS,
            activities=ACTIVITIES,
            activity_executor=executor,
        )
        logger.info("воркер запущен: очередь=%s", settings.temporal_task_queue)
        await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
