import asyncio
import logging
from uuid import uuid4

import pytest

from app.domain.exceptions import (
    CancelCompletedTask,
    ProcessCompletedTask,
    ProcessProcessingTask,
    TaskNotFoundError,
)
from app.domain.tasks import TaskStatus
from app.repositories.tasks import InMemoryTaskRepository, ITaskRepository
from app.use_cases.tasks import TaskUseCase


@pytest.fixture
def tasks_repository() -> ITaskRepository:
    return InMemoryTaskRepository()


@pytest.fixture
def app_task_use_case(tasks_repository: InMemoryTaskRepository) -> TaskUseCase:
    logger = logging.getLogger(__name__)
    return TaskUseCase(tasks_repository, logger)


@pytest.fixture
def worker_task_use_case(tasks_repository: InMemoryTaskRepository) -> TaskUseCase:
    logger = logging.getLogger(__name__)
    task_use_case = TaskUseCase(tasks_repository, logger)
    task_use_case.sleep_time = 1
    return task_use_case


@pytest.mark.asyncio
async def test_get_task_not_found(app_task_use_case: TaskUseCase):
    with pytest.raises(TaskNotFoundError):
        await app_task_use_case.get_task(task_id=str(uuid4()))


@pytest.mark.asyncio
async def test_cancel_task_not_found(app_task_use_case: TaskUseCase):
    with pytest.raises(TaskNotFoundError):
        await app_task_use_case.cancel_task(task_id=str(uuid4()))


@pytest.mark.asyncio
async def test_cancel_task_on_completed_task(app_task_use_case: TaskUseCase, worker_task_use_case: TaskUseCase):
    task = await app_task_use_case.create_task(payload="test")
    await worker_task_use_case.run_task(task_id=task.id)
    with pytest.raises(CancelCompletedTask):
        await app_task_use_case.cancel_task(task_id=task.id)


@pytest.mark.asyncio
async def test_run_task_successfully(app_task_use_case: TaskUseCase, worker_task_use_case: TaskUseCase):
    payload = "test"
    task = await app_task_use_case.create_task(payload=payload)
    worker_processing_task = asyncio.create_task(worker_task_use_case.run_task(task_id=task.id))
    await asyncio.sleep(0)
    assert task.status == TaskStatus.processing
    await worker_processing_task
    assert task.status == TaskStatus.completed
    assert task.result == str(len(payload))
    assert task.error is None


@pytest.mark.asyncio
async def test_cancel_task_before_processing(app_task_use_case: TaskUseCase, worker_task_use_case: TaskUseCase):
    task = await app_task_use_case.create_task(payload="test")
    worker_processing_task = asyncio.create_task(worker_task_use_case.run_task(task_id=task.id))
    await asyncio.sleep(0)
    await app_task_use_case.cancel_task(task_id=task.id)
    await worker_processing_task
    assert task.status == TaskStatus.canceled


@pytest.mark.asyncio
async def test_worker_run_processing_task(app_task_use_case: TaskUseCase, worker_task_use_case: TaskUseCase):
    task = await app_task_use_case.create_task(payload="test")
    worker_processing_task = asyncio.create_task(worker_task_use_case.run_task(task_id=task.id))
    await asyncio.sleep(0)
    with pytest.raises(ProcessProcessingTask):
        await worker_task_use_case.run_task(task_id=task.id)
    await worker_processing_task


@pytest.mark.asyncio
async def test_worker_run_completed_task(app_task_use_case: TaskUseCase, worker_task_use_case: TaskUseCase):
    task = await app_task_use_case.create_task(payload="test")
    await worker_task_use_case.run_task(task_id=task.id)
    with pytest.raises(ProcessCompletedTask):
        await worker_task_use_case.run_task(task_id=task.id)


@pytest.mark.asyncio
async def test_worker_run_bulk_tasks(app_task_use_case: TaskUseCase, worker_task_use_case: TaskUseCase):
    payload1 = "1"
    payload2 = "12"
    payload3 = "123"
    task1 = await app_task_use_case.create_task(payload=payload1)
    task2 = await app_task_use_case.create_task(payload=payload2)
    task3 = await app_task_use_case.create_task(payload=payload3)
    await app_task_use_case.cancel_task(task_id=task2.id)

    await worker_task_use_case.run_tasks(task_ids=[task1.id, task2.id, task3.id])
    assert task1.status == TaskStatus.completed
    assert task1.result == str(len(payload1))
    assert task1.error is None

    assert task2.status == TaskStatus.canceled
    assert task2.result is None
    assert task2.error is None

    assert task3.status == TaskStatus.completed
    assert task3.result == str(len(payload3))
    assert task3.error is None
