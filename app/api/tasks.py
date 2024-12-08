from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.dependency import get_task_creation_use_case, get_task_use_case
from app.domain.tasks import Task, TaskSchema
from app.use_cases.tasks import TaskCreationUseCase, TaskUseCase

router: APIRouter = APIRouter(tags=["tasks"])


@router.get("/tasks/{task_id}", description="Get a task.", response_model=TaskSchema)
async def get_task(
    task_id: str,
    use_case: TaskUseCase = Depends(get_task_use_case),
) -> Task:
    return await use_case.get_task(task_id)


class CreateTaskSchema(BaseModel):
    payload: str


@router.post("/tasks", description="Create a task.", response_model=TaskSchema)
async def create_task(data: CreateTaskSchema, use_case: TaskCreationUseCase = Depends(get_task_creation_use_case)) -> Task:
    return await use_case.create_task(payload=data.payload)


@router.post("/tasks/{task_id}:cancel", description="Cancel a task.", response_model=TaskSchema)
async def cancel_task(task_id: str, use_case: TaskUseCase = Depends(get_task_use_case)) -> Task:
    return await use_case.cancel_task(task_id)
