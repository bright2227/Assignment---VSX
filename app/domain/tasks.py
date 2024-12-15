"""
Class definition for Task
"""

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict
from sqlalchemy import false, func, text
from sqlalchemy.orm import Mapped, declarative_base, mapped_column
from sqlalchemy.types import BOOLEAN, DateTime, Text


class TaskStatus(str, Enum):
    pending = "pending"
    canceled = "canceled"
    processing = "processing"
    completed = "completed"


Base = declarative_base()


class Task(Base):
    """
    Database class for Task
    """

    __tablename__ = "task"
    id: Mapped[str] = mapped_column("id", Text, primary_key=True, server_default=text("uuid_generate_v4()"))
    status: Mapped[TaskStatus] = mapped_column("status", Text, nullable=False)
    payload: Mapped[str] = mapped_column("payload", Text, nullable=False)
    result: Mapped[str | None] = mapped_column("result", Text, nullable=True)
    error: Mapped[str | None] = mapped_column("error", Text, nullable=True)
    submit: Mapped[bool] = mapped_column("submit", BOOLEAN, nullable=False, server_default=false())
    created_time: Mapped[datetime] = mapped_column(
        "created_time", DateTime, nullable=False, index=True, server_default=func.now()
    )
    updated_time: Mapped[datetime] = mapped_column(
        "updated_time",
        DateTime,
        server_default=func.now(),
        onupdate=datetime.now(timezone.utc).replace(tzinfo=None),
        nullable=False,
    )
    # below the updated_time is determined by postgres, it would causes trouble when updating the ORm object via assign values
    # updated_time would becomes expired_attributes and raise
    # https://docs.sqlalchemy.org/en/20/errors.html#parent-instance-x-is-not-bound-to-a-session-lazy-load-deferred-load-refresh-etc-operation-cannot-proceed
    # updated_time: Mapped[datetime] = mapped_column(
    #     "updated_time", DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    # )


class TaskSchema(BaseModel):
    id: str
    status: TaskStatus
    payload: str
    result: str | None
    error: str | None
    created_time: datetime
    updated_time: datetime
    submit: bool
    model_config = ConfigDict(from_attributes=True)
