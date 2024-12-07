from datetime import datetime, timezone
from typing import Callable, List, Optional, Protocol
from uuid import uuid4

from aio_pika import Message
from aio_pika.abc import AbstractExchange
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_scoped_session

from app.domain.exceptions import TaskNotFoundError
from app.domain.tasks import Task, TaskStatus


class ITaskRepository(Protocol):
    async def get_task(self, task_id: str) -> Task: ...

    async def list_tasks(
        self, created_time_lt: datetime | None = None, limit: int = 100, submit: bool | None = None
    ) -> List[Task]: ...

    async def create_task(self, payload: str) -> Task: ...

    async def update_task(self, task_id: str, update_func: Callable[[Task], None]) -> Task: ...

    async def update_tasks(self, task_ids: list[str], update_func: Callable[[list[Task]], None]) -> list[Task]: ...

    async def resubmit_task(self, task: Task) -> None: ...


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
        self, created_time_lt: datetime | None = None, limit: int = 100, submit: bool | None = None
    ) -> List[Task]:
        query = select(Task)
        if created_time_lt is not None:
            query = query.where(Task.created_time < created_time_lt)
        if submit is not None:
            query = query.where(Task.submit.is_(submit))
        if limit is not None:
            query = query.limit(limit)

        query = query.order_by(Task.created_time)
        async with self.session_factory() as session:
            result = await session.execute(query)
            return list(result.scalars().all())

    async def create_task(self, payload: str) -> Task:
        async with self.session_factory() as session:
            task = Task(id=str(uuid4()), payload=payload, status=TaskStatus.pending, submit=False)
            session.add(task)
            await session.commit()
            await self.direct_exchange.publish(
                Message(task.id.encode(), content_type="text/plain"),
                routing_key=self.task_routing_key,
            )
            task.submit = True
            await session.commit()
            await session.refresh(task)
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

    async def resubmit_task(self, task: Task) -> None:
        async with self.session_factory() as session:
            if task.status == TaskStatus.pending:
                await self.direct_exchange.publish(
                    Message(task.id.encode(), content_type="text/plain"),
                    routing_key=self.task_routing_key,
                )
            await session.execute(update(Task).values(submit=True).where(Task.id == task.id))
            await session.commit()


class InMemoryTaskRepository(ITaskRepository):
    def __init__(self, tasks: Optional[dict[str, Task]] = None):
        self._task_map = tasks if tasks else {}

    async def get_task(self, task_id: str) -> Task:
        if task_id not in self._task_map:
            raise TaskNotFoundError(task_id=task_id)
        return self._task_map[task_id]

    async def list_tasks(
        self, created_time_lt: datetime | None = None, limit: int = 100, submit: bool | None = None
    ) -> List[Task]:
        tasks = [task for task in self._task_map.values()]
        if created_time_lt is not None:
            tasks = [task for task in tasks if task.created_time < created_time_lt]
        if submit is not None:
            tasks = [task for task in tasks if task.submit == submit]
        if limit is not None:
            tasks = tasks[:limit]
        return sorted(tasks, key=lambda task: task.created_time)

    async def create_task(self, payload: str) -> Task:
        task = Task(
            id=str(uuid4()),
            status=TaskStatus.pending,
            payload=payload,
            created_time=datetime.now(timezone.utc),
            updated_time=datetime.now(timezone.utc),
            submit=False,
        )
        self._task_map[task.id] = task
        task.submit = True
        return task

    async def update_task(self, task_id: str, update_func: Callable[[Task], None]) -> Task:
        task = await self.get_task(task_id)
        update_func(task)
        return task

    async def update_tasks(self, task_ids: list[str], update_func: Callable[[list[Task]], None]) -> list[Task]:
        tasks = [self._task_map.get(task_id) for task_id in task_ids if task_id in self._task_map]
        update_func(tasks)
        return tasks

    async def resubmit_task(self, task: Task) -> None:
        task.submit = True
        return
