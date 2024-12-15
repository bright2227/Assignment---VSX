from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Callable, List, Optional, Protocol
from uuid import uuid4

from aio_pika import Message
from aio_pika.abc import AbstractExchange
from sqlalchemy import Text, cast, column, insert, inspect, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_scoped_session
from sqlalchemy.sql import Values

from app.domain.exceptions import TaskNotFoundError
from app.domain.tasks import Task, TaskStatus


class ITaskRepository(Protocol):
    async def get_task(self, task_id: str) -> Task: ...

    async def list_tasks(
        self, created_time_gt: datetime | None = None, limit: int = 100, submit: bool | None = None
    ) -> List[Task]: ...

    async def create_task(self, task: Task) -> Task: ...

    async def update_task(self, task_id: str, update_func: Callable[[Task], None]) -> Task: ...

    async def update_tasks(self, task_ids: list[str], update_func: Callable[[list[Task]], None]) -> list[Task]: ...

    async def submit_task(self, task: Task) -> None: ...


class ITaskCreationRepository(Protocol):
    async def create_and_submit_task(self, payload: str) -> Task: ...

    async def rerun_non_submit_tasks(self): ...


class ITaskProcessingRepository(Protocol):
    async def set_pending_tasks_processing(self, task_ids: list[str]) -> list[Task | None]: ...

    async def set_result_on_processing_tasks(self, tasks_result: list[tuple[str, str | None, str | None]]) -> list[Task]: ...


class SqlTaskRepository(ITaskRepository):
    def __init__(
        self, session_factory: async_scoped_session[AsyncSession], direct_exchange: AbstractExchange, task_routing_key: str
    ):
        self.session_factory = session_factory
        self.direct_exchange = direct_exchange
        self.task_routing_key = task_routing_key

    async def get_task(self, task_id: str) -> Task:
        async with self.session_factory() as session:
            try:
                result = await session.execute(select(Task).where(Task.id == task_id))
                task = result.scalars().one_or_none()
                if not task:
                    raise TaskNotFoundError(task_id=task_id)
                return task
            finally:
                await session.close()

    async def list_tasks(
        self, created_time_gt: datetime | None = None, limit: int = 100, submit: bool | None = None
    ) -> List[Task]:
        query = select(Task)
        if created_time_gt is not None:
            query = query.where(Task.created_time > created_time_gt)
        if submit is not None:
            query = query.where(Task.submit.is_(submit))
        if limit is not None:
            query = query.limit(limit)

        query = query.order_by(Task.created_time)
        async with self.session_factory() as session:
            result = await session.execute(query)
            return list(result.scalars().all())

    async def create_task(self, task: Task) -> Task:
        async with self.session_factory() as session:
            session.add(task)
            await session.commit()
            return task

    async def update_task(self, task_id: str, update_func: Callable[[Task], None]) -> Task:
        async with self.session_factory() as session:
            result = await session.execute(select(Task).where(Task.id == task_id).with_for_update())
            task = result.scalars().one_or_none()
            if not task:
                raise TaskNotFoundError(task_id=task_id)
            update_func(task)
            await session.commit()
            return task

    async def update_tasks(self, task_ids: list[str], update_func: Callable[[list[Task]], None]) -> list[Task]:
        async with self.session_factory() as session:
            result = await session.execute(select(Task).where(Task.id.in_(task_ids)).with_for_update())
            tasks = list(result.scalars().all())
            update_func(tasks)
            await session.commit()
            return tasks

    async def submit_task(self, task: Task) -> None:
        await self.direct_exchange.publish(
            Message(task.id.encode(), content_type="text/plain"),
            routing_key=self.task_routing_key,
        )


class TaskCreationRepository(ITaskCreationRepository):
    def __init__(self, engine: AsyncEngine, direct_exchange: AbstractExchange, task_routing_key: str):
        self.engine = engine
        self.direct_exchange = direct_exchange
        self.task_routing_key = task_routing_key

    async def create_and_submit_task(self, payload: str) -> Task:
        task_id = str(uuid4())
        async with start_transaction(self.engine) as connection:
            await connection.execute(insert(Task).values(id=task_id, payload=payload, status=TaskStatus.pending, submit=False))

        await self._submit_task_id_to_mq(task_id=task_id)

        async with start_transaction(self.engine) as connection:
            result = await connection.execute(update(Task).values(submit=True).where(Task.id == task_id).returning(Task))

        task_data = result.mappings().one_or_none()
        if not task_data:
            raise TaskNotFoundError(task_id=task_id)
        return Task(**task_data)

    async def rerun_non_submit_tasks(self):
        last_created_time = None
        while True:
            query = select(Task).where(Task.submit.is_(False))
            if last_created_time:
                query = query.where(Task.created_time > last_created_time)

            async with start_transaction(self.engine) as connection:
                result = await connection.execute(query)

            tasks = list(result.scalars().all())
            if not tasks:
                return

            last_created_time = tasks[-1].created_time
            for task in tasks:
                await self._submit_task_id_to_mq(task_id=task.id)
                async with start_transaction(self.engine) as connection:
                    await connection.execute(update(Task).values(submit=True).where(Task.id == task.id))

    async def _submit_task_id_to_mq(self, task_id: str):
        await self.direct_exchange.publish(
            Message(task_id.encode(), content_type="text/plain"),
            routing_key=self.task_routing_key,
        )


class TaskProcessingRepository(ITaskProcessingRepository):
    def __init__(self, engine: AsyncEngine):
        self.engine = engine

    async def set_pending_tasks_processing(self, task_ids: list[str]) -> list[Task | None]:
        update_query = (
            update(Task).values(status=TaskStatus.processing).where(Task.id.in_(task_ids), Task.status == TaskStatus.pending)
        )
        async with start_transaction(self.engine) as connection:
            await connection.execute(update_query)
            result = await connection.execute(select(Task).where(Task.id.in_(task_ids)))

        task_map = {task_data["id"]: Task(**task_data) for task_data in result.mappings().all()}
        return [task_map.get(task_id, None) for task_id in task_ids]

    async def set_result_on_processing_tasks(self, tasks_result: list[tuple[str, str | None, str | None]]) -> list[Task]:
        task_ids: list[str] = []
        tasks_update_data = []
        for task_id, result, error in tasks_result:
            task_ids.append(task_id)
            tasks_update_data.append(
                (
                    task_id,
                    optional_value(result, Text),
                    optional_value(error, Text),
                )
            )

        tasks_update = Values(
            column("id", Text),
            column("result", Text),
            column("error", Text),
            name="tasks_update",
        ).data(tasks_update_data)

        update_query = (
            update(Task)
            .values(result=tasks_update.c.result, error=tasks_update.c.error, status=TaskStatus.completed)
            .where(Task.id == tasks_update.c.id, Task.status == TaskStatus.processing)
        )
        async with start_transaction(self.engine) as connection:
            await connection.execute(update_query)
            result = await connection.execute(select(Task).where(Task.id.in_(task_ids)))
            await connection.commit()

        task_map = {task_data["id"]: Task(**task_data) for task_data in result.mappings().all()}
        return [task_map[task_id] for task_id in task_ids]


class InMemoryTaskRepository(ITaskRepository, ITaskCreationRepository, ITaskProcessingRepository):
    def __init__(self, tasks: Optional[dict[str, Task]] = None):
        self._task_map = tasks if tasks else {}

    async def get_task(self, task_id: str) -> Task:
        if task_id not in self._task_map:
            raise TaskNotFoundError(task_id=task_id)
        return self._task_map[task_id]

    async def list_tasks(
        self, created_time_gt: datetime | None = None, limit: int = 100, submit: bool | None = None
    ) -> List[Task]:
        tasks = [task for task in self._task_map.values()]
        if created_time_gt is not None:
            tasks = [task for task in tasks if task.created_time > created_time_gt]
        if submit is not None:
            tasks = [task for task in tasks if task.submit == submit]
        if limit is not None:
            tasks = tasks[:limit]
        return sorted(tasks, key=lambda task: task.created_time)

    async def create_task(self, task: Task) -> Task:
        task_id = str(uuid4())
        task.id = task_id
        self._task_map[task_id] = task
        task.created_time = datetime.now(timezone.utc)
        task.updated_time = datetime.now(timezone.utc)
        return task

    async def update_task(self, task_id: str, update_func: Callable[[Task], None]) -> Task:
        task = await self.get_task(task_id)
        update_func(task)
        task.updated_time = datetime.now(timezone.utc)
        return task

    async def update_tasks(self, task_ids: list[str], update_func: Callable[[list[Task]], None]) -> list[Task]:
        tasks = [self._task_map[task_id] for task_id in task_ids if task_id in self._task_map]
        update_func(tasks)
        now = datetime.now(timezone.utc)
        for task in tasks:
            task.updated_time = now
        return tasks

    async def submit_task(self, task: Task) -> None:
        # TODO: implement a in memory queue
        return

    async def create_and_submit_task(self, payload: str) -> Task:
        task = await self.create_task(Task(payload=payload, status=TaskStatus.pending, submit=False))
        await self.submit_task(task)
        return task

    async def rerun_non_submit_tasks(self):
        for task in self._task_map.values():
            if not task.submit:
                task.submit = True
                await self.submit_task(task)
        return

    async def set_pending_tasks_processing(self, task_ids: list[str]) -> list[Task | None]:
        tasks = []
        for task_id in task_ids:
            task = self._task_map.get(task_id, None)
            if task and task.status == TaskStatus.pending:
                task.status = TaskStatus.processing
            tasks.append(task)
        return tasks

    async def set_result_on_processing_tasks(self, tasks_result: list[tuple[str, str | None, str | None]]) -> list[Task]:
        tasks = []
        for task_id, result, error in tasks_result:
            task = self._task_map[task_id]
            if task.status == TaskStatus.processing:
                task.result = result
                task.error = error
            tasks.append(task)
        return tasks


@asynccontextmanager
async def start_transaction(engine: AsyncEngine, isolation_level: str = "AUTOCOMMIT"):
    async with engine.connect() as connection:
        await connection.execution_options(isolation_level=isolation_level)
        async with connection.begin():
            yield connection


def optional_value(value, type_):
    return cast(None, type_) if value is None else value
