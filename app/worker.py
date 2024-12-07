import asyncio
import logging.config

from aio_pika.abc import AbstractIncomingMessage

from app.config import postgres as sql
from app.config import rabbitmq as mq
from app.config.config import Settings
from app.repositories.tasks import SqlTaskRepository
from app.use_cases.tasks import TaskUseCase


async def main():
    settings = Settings()  # type: ignore
    LOGGING_CONFIG = {
        "version": 1,
        "disable_existing_loggers": True,
        "formatters": {
            "standard": {"format": "[%(asctime)s.%(msecs)03d][%(levelname)s]: %(message)s"},
        },
        "handlers": {
            "default": {
                "level": settings.LOG_LEVEL,
                "formatter": "standard",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",  # Default is stderr
            },
        },
        "loggers": {
            "": {  # root logger
                "level": settings.LOG_LEVEL,  # "INFO",
                "handlers": ["default"],
                "propagate": False,
            }
        },
    }
    logging.config.dictConfig(LOGGING_CONFIG)
    logger = logging.getLogger()

    mq_resources_manager = await mq.ResourcesManager.initialize(settings)
    sql_resources_manager = await sql.ResourcesManager.initialize(settings)
    messages: list[AbstractIncomingMessage] = []
    task_use_case = TaskUseCase(
        task_repository=SqlTaskRepository(
            session_factory=sql_resources_manager.session_factory,
            direct_exchange=mq_resources_manager.direct_exchange,
            task_routing_key=mq_resources_manager.task_routing_key,
        ),
        logger=logger,
    )
    messages_chunk_size = mq_resources_manager.task_prefetch_count

    async def bulk_processing():
        nonlocal messages
        while True:
            if not messages:
                await asyncio.sleep(1)
                continue
            processing_messages = messages[:messages_chunk_size]
            messages = messages[messages_chunk_size:]
            await task_use_case.run_tasks([message.body.decode() for message in processing_messages])
            await processing_messages[-1].ack(multiple=True)

    async def get_tasks():
        queue = mq_resources_manager.tasks_queue
        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                messages.append(message)

    try:
        await asyncio.gather(bulk_processing(), get_tasks())
    finally:
        await mq_resources_manager.shutdown()
        await sql_resources_manager.shutdown()


if __name__ == "__main__":
    asyncio.run(main())