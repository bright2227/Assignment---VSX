import logging
from typing import cast

import aio_pika
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_scoped_session

from app.repositories.tasks import (
    ITaskCreationRepository,
    ITaskRepository,
    SqlTaskRepository,
    TaskCreationRepository,
)
from app.use_cases.tasks import TaskCreationUseCase, TaskUseCase


def get_task_repository(request: Request) -> ITaskRepository:
    session_factory = cast(async_scoped_session[AsyncSession], request.app.sql_resources_manager.session_factory)
    direct_exchange = cast(aio_pika.abc.AbstractExchange, request.app.mq_resources_manager.direct_exchange)
    task_routing_key = cast(str, request.app.mq_resources_manager.task_routing_key)
    return SqlTaskRepository(
        session_factory=session_factory, direct_exchange=direct_exchange, task_routing_key=task_routing_key
    )


def get_task_use_case(task_repository: ITaskRepository = Depends(get_task_repository)) -> TaskUseCase:
    logger = logging.getLogger("uvicorn")
    return TaskUseCase(task_repository, logger=logger)


def get_task_creation_repository(request: Request) -> ITaskCreationRepository:
    engine = cast(AsyncEngine, request.app.sql_resources_manager.engine)
    direct_exchange = cast(aio_pika.abc.AbstractExchange, request.app.mq_resources_manager.direct_exchange)
    task_routing_key = cast(str, request.app.mq_resources_manager.task_routing_key)
    return TaskCreationRepository(engine=engine, direct_exchange=direct_exchange, task_routing_key=task_routing_key)


def get_task_creation_use_case(
    task_repository: ITaskCreationRepository = Depends(get_task_creation_repository),
) -> TaskCreationUseCase:
    logger = logging.getLogger("uvicorn")
    return TaskCreationUseCase(task_repository, logger=logger)
