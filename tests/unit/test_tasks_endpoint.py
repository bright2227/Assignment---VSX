import logging
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.dependency import get_tasks_repository
from app.domain.exceptions import CancelCompletedTask, TaskNotFoundError
from app.domain.tasks import TaskSchema, TaskStatus
from app.main import app
from app.repositories.tasks import InMemoryTaskRepository, ITaskRepository
from app.use_cases.tasks import TaskUseCase


@pytest.fixture
def tasks_repository() -> ITaskRepository:
    return InMemoryTaskRepository()


@pytest.fixture
def test_client(tasks_repository: ITaskRepository) -> TestClient:
    client = TestClient(app)
    app.dependency_overrides[get_tasks_repository] = lambda: tasks_repository
    return client


@pytest.fixture
def test_worker(tasks_repository: ITaskRepository) -> TaskUseCase:
    logger = logging.getLogger(__name__)
    task_use_case = TaskUseCase(tasks_repository, logger)
    task_use_case.sleep_time = 1
    return task_use_case


def test_get_task_not_found(test_client: TestClient):
    task_id = str(uuid4())
    response = test_client.get("/tasks/{task_id}".format(task_id=task_id))
    assert response.status_code == 404
    assert response.json() == {"message": str(TaskNotFoundError(task_id=task_id))}


def test_cancel_task_not_found(test_client: TestClient):
    task_id = str(uuid4())
    response = test_client.post("/tasks/{task_id}:cancel".format(task_id=task_id))
    assert response.status_code == 404
    assert response.json() == {"message": str(TaskNotFoundError(task_id=task_id))}


@pytest.mark.asyncio
async def test_cancel_task_on_completed_task(test_client: TestClient, test_worker: TaskUseCase):
    response = test_client.post("/tasks", json={"payload": "test"})
    assert response.status_code == 200
    task = TaskSchema.model_validate(response.json())
    await test_worker.run_task(task.id)

    response = test_client.post("/tasks/{task_id}:cancel".format(task_id=task.id))
    assert response.status_code == 422
    assert response.json() == {"message": str(CancelCompletedTask(task_id=task.id))}


@pytest.mark.asyncio
async def test_run_task_successfully(test_client: TestClient, test_worker: TaskUseCase):
    payload = "test"
    response = test_client.post("/tasks", json={"payload": payload})
    assert response.status_code == 200
    task = TaskSchema.model_validate(response.json())
    await test_worker.run_task(task.id)

    response = test_client.get("/tasks/{task_id}".format(task_id=task.id))
    assert response.status_code == 200
    task = TaskSchema.model_validate(response.json())
    assert task.status == TaskStatus.completed
    assert task.result == str(len(payload))


def test_cancel_task_before_processing(test_client: TestClient):
    response = test_client.post("/tasks", json={"payload": "test"})
    assert response.status_code == 200
    task = TaskSchema.model_validate(response.json())

    response = test_client.post("/tasks/{task_id}:cancel".format(task_id=task.id))
    assert response.status_code == 200
    task = TaskSchema.model_validate(response.json())
    assert task.status == TaskStatus.canceled
    assert task.result is None
