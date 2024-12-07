import asyncio
from datetime import datetime
from functools import partial
from logging import Logger
from typing import List

from app.domain.exceptions import (
    CancelCompletedTask,
    ProcessCompletedTask,
    ProcessProcessingTask,
    TaskNotFoundError,
)
from app.domain.tasks import Task, TaskStatus
from app.repositories.tasks import ITaskRepository


class TaskUseCase:
    def __init__(self, task_repository: ITaskRepository, logger: Logger) -> None:
        self.task_repository = task_repository
        self.sleep_time = 3
        self.logger = logger

    async def create_task(self, payload: str) -> Task:
        return await self.task_repository.create_task(payload)

    async def get_task(self, task_id: str) -> Task:
        return await self.task_repository.get_task(task_id)

    async def cancel_task(self, task_id: str) -> Task:
        return await self.task_repository.update_task(task_id, self._cancel_task)

    def _cancel_task(self, task: Task) -> None:
        if task.status == TaskStatus.completed:
            raise CancelCompletedTask(task_id=task.id)
        task.status = TaskStatus.canceled

    async def run_tasks(self, task_ids: list[str]) -> None:
        existed_tasks = await self.task_repository.update_tasks(task_ids, self._run_tasks_start)
        for task_id in set(task_ids).difference(set([task.id for task in existed_tasks])):
            self.logger.error(f"task: {task_id} got error: {TaskNotFoundError(task_id=task_id)}")
        processing_tasks = [task for task in existed_tasks if task.status == TaskStatus.processing]
        processing_task_ids = [task.id for task in processing_tasks]
        tasks_result = await asyncio.gather(*[self._process_task_content(task=task) for task in processing_tasks])
        results_map = {task_id: task_result for task_id, task_result in zip(processing_task_ids, tasks_result)}
        await self.task_repository.update_tasks(processing_task_ids, partial(self._run_tasks_end, results_map=results_map))

    def _run_tasks_start(self, tasks: list[Task]) -> None:
        for task in tasks:
            if task.status == TaskStatus.canceled:
                self.logger.info(f"task: {task.id} is canceled.")
            elif task.status == TaskStatus.completed:
                self.logger.error(f"task: {task.id} got error: {ProcessCompletedTask(task_id=task.id)}")
            elif task.status == TaskStatus.processing:
                self.logger.error(f"task: {task.id} got error: {ProcessProcessingTask(task_id=task.id)}")
            else:
                task.status = TaskStatus.processing

    def _run_tasks_end(self, tasks: list[Task], results_map: dict[str, tuple[str | None, str | None]]) -> None:
        for task in tasks:
            if task.status == TaskStatus.canceled:
                self.logger.info(f"task: {task.id} is canceled.")
                return
            result, error = results_map[task.id]
            task.status = TaskStatus.completed
            task.result = result
            task.error = error
            self.logger.info(f"task: {task.id} is completed.")

    async def run_task(self, task_id: str) -> None:
        task = await self.task_repository.update_task(task_id, self._run_task_start)
        if task.status == TaskStatus.canceled:
            return
        results_map = {task.id: await self._process_task_content(task=task)}
        await self.task_repository.update_task(task_id, partial(self._run_task_end, results_map=results_map))

    def _run_task_start(self, task: Task) -> None:
        if task.status == TaskStatus.canceled:
            self.logger.info(f"task: {task.id} is canceled.")
        elif task.status == TaskStatus.completed:
            error = ProcessCompletedTask(task_id=task.id)
            self.logger.error(f"task: {task.id} got error: {error}")
            raise error
        elif task.status == TaskStatus.processing:
            error = ProcessProcessingTask(task_id=task.id)
            self.logger.error(f"task: {task.id} got error: {error}")
            raise error
        else:
            task.status = TaskStatus.processing

    def _run_task_end(
        self,
        task: Task,
        results_map: dict[str, tuple[str | None, str | None]],
    ) -> None:
        if task.status == TaskStatus.canceled:
            return
        result, error = results_map[task.id]
        task.status = TaskStatus.completed
        task.result = result
        task.error = error
        self.logger.info(f"task: {task.id} is completed.")

    async def _process_task_content(self, task: Task) -> tuple[str | None, str | None]:
        await asyncio.sleep(self.sleep_time)
        return (str(len(task.payload)) if task.payload else "0", None)

    async def rerun_non_submit_tasks(self):
        """To make sure at once delivery on publisher side."""
        last_created_time = None
        while True:
            tasks = await self.task_repository.list_tasks(submit=False, created_time_lt=last_created_time)
            if not tasks:
                return

            last_created_time = tasks[-1].created_time
            for task in tasks:
                await self.task_repository.resubmit_task(task)
