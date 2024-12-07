from aio_pika.exceptions import AMQPError
from sqlalchemy.exc import SQLAlchemyError


class TaskNotFoundError(Exception):
    def __init__(self, task_id: str):
        self.task_id = task_id

    def __str__(self) -> str:
        return f"Task: {self.task_id} not found."


class CancelCompletedTask(Exception):
    def __init__(self, task_id: str):
        self.task_id = task_id

    def __str__(self) -> str:
        return f"Task: {self.task_id} can not can canceled because the status is completed."


class ProcessCompletedTask(Exception):
    def __init__(self, task_id: str):
        self.task_id = task_id

    def __str__(self) -> str:
        return f"Task: {self.task_id} can not can processed because the status is completed."


class ProcessProcessingTask(Exception):
    def __init__(self, task_id: str):
        self.task_id = task_id

    def __str__(self) -> str:
        return f"Task: {self.task_id} can not can processed because the status is processing."


class SqlError(SQLAlchemyError):
    pass


class MessageQueueError(AMQPError):
    pass
