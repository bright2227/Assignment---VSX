import asyncio
from contextlib import suppress
from dataclasses import dataclass

import aio_pika
from aio_pika.abc import (
    AbstractChannel,
    AbstractConnection,
    AbstractExchange,
    AbstractQueue,
    ExchangeType,
)
from fastapi import FastAPI

from app.config.config import Settings


@dataclass
class ResourcesManager:
    connection: AbstractConnection
    channel: AbstractChannel
    direct_exchange: AbstractExchange
    tasks_queue: AbstractQueue
    task_routing_key: str = "tasks"
    task_queue_name: str = "tasks"
    task_prefetch_count: int = 400
    x_message_ttl: int = 30000

    @classmethod
    async def initialize(cls, settings: Settings) -> "ResourcesManager":
        loop = asyncio.get_event_loop()
        connection: AbstractConnection | None = None
        retry_times = 5
        for i in range(1, retry_times + 1):
            try:
                connection = await aio_pika.connect_robust(str(settings.RABBITMQ_DSN), loop=loop)
            except aio_pika.exceptions.AMQPConnectionError as e:
                if i == retry_times:
                    raise e
                await asyncio.sleep(3)

        assert connection is not None

        channel = await connection.channel()
        task_routing_key = cls.task_routing_key
        task_queue_name = cls.task_queue_name
        task_prefetch_count = cls.task_prefetch_count
        await channel.set_qos(task_prefetch_count)

        direct_exchange = await channel.declare_exchange(
            "direct", type=ExchangeType.DIRECT, auto_delete=False, durable=True, passive=False
        )

        tasks_queue = await channel.declare_queue(
            task_queue_name, auto_delete=False, durable=True, passive=False, arguments={"x-message-ttl": cls.x_message_ttl}
        )
        await tasks_queue.bind(direct_exchange, task_routing_key)

        return cls(
            connection=connection,
            channel=channel,
            direct_exchange=direct_exchange,
            tasks_queue=tasks_queue,
            task_routing_key=task_routing_key,
        )

    async def shutdown(self):
        with suppress(BaseException):
            await self.connection.close()


async def init(app: FastAPI, settings: Settings):
    app.mq_resources_manager = await ResourcesManager.initialize(settings)  # type: ignore


async def shutdown(app: FastAPI):
    with suppress(BaseException):
        await app.mq_resources_manager.shutdown()  # type: ignore
