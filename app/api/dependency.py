import logging
from typing import cast

import aio_pika
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_scoped_session

from app.repositories.tasks import ITaskRepository, SqlTaskRepository
from app.use_cases.tasks import TaskUseCase


def get_tasks_repository(request: Request) -> ITaskRepository:
    session_factory = cast(async_scoped_session[AsyncSession], request.app.sql_resources_manager.session_factory)
    direct_exchange = cast(aio_pika.abc.AbstractExchange, request.app.mq_resources_manager.direct_exchange)
    task_routing_key = cast(str, request.app.mq_resources_manager.task_routing_key)
    return SqlTaskRepository(
        session_factory=session_factory, direct_exchange=direct_exchange, task_routing_key=task_routing_key
    )


def get_tasks_use_case(tasks_repository: ITaskRepository = Depends(get_tasks_repository)) -> TaskUseCase:
    logger = logging.getLogger("uvicorn")
    return TaskUseCase(tasks_repository, logger=logger)
