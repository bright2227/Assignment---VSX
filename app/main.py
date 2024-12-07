import asyncio
import logging
import logging.config
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.api.tasks import router
from app.config import postgres as sql
from app.config import rabbitmq as mq
from app.config.config import Settings
from app.domain.exceptions import (
    CancelCompletedTask,
    MessageQueueError,
    SqlError,
    TaskNotFoundError,
)
from app.repositories.tasks import SqlTaskRepository
from app.use_cases.tasks import TaskUseCase

logger = logging.getLogger("uvicorn")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()  # type: ignore
    LOGGING_CONFIG = {
        "version": 1,
        "disable_existing_loggers": True,
        "formatters": {
            "standard": {"format": "[%(asctime)s.%(msecs)03d][%(levelname)s]: %(message)s"},
        },
        "handlers": {
            "default": {
                "level": settings.LOG_LEVEL,
                "formatter": "standard",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",  # Default is stderr
            },
        },
        "loggers": {
            "": {  # root logger
                "level": settings.LOG_LEVEL,  # "INFO",
                "handlers": ["default"],
                "propagate": False,
            },
            "uvicorn.error": {
                "level": "DEBUG",
                "handlers": [],
            },
            "uvicorn.access": {
                "level": "DEBUG",
                "handlers": [],
            },
            "uvicorn": {
                "level": "DEBUG",
                "handlers": ["default"],
            },
        },
    }
    logging.config.dictConfig(LOGGING_CONFIG)
    await sql.init(app, settings)
    await mq.init(app, settings)

    async def rerun_non_submit_tasks():
        """Make sure two phase commit if server crash."""
        try:
            task_use_case = TaskUseCase(
                task_repository=SqlTaskRepository(
                    session_factory=app.sql_resources_manager.session_factory,  # type: ignore
                    direct_exchange=app.mq_resources_manager.direct_exchange,  # type: ignore
                    task_routing_key=app.mq_resources_manager.task_routing_key,  # type: ignore
                ),
                logger=logger,
            )
            await task_use_case.rerun_non_submit_tasks()
        except Exception as e:
            logger.exception(f"rerun_non_submit_tasks got error: {e}")

    task = asyncio.create_task(rerun_non_submit_tasks())
    yield
    await mq.shutdown(app)
    await sql.shutdown(app)
    task.cancel()


app = FastAPI(lifespan=lifespan)
app.include_router(router)


@app.exception_handler(TaskNotFoundError)
async def task_not_found_exception_handler(request: Request, exc: TaskNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"message": str(exc)})


@app.exception_handler(CancelCompletedTask)
async def cancel_complete_task_exception_handler(request: Request, exc: CancelCompletedTask) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"message": str(exc)},
    )


@app.exception_handler(SqlError)
async def database_exception_handler(request: Request, exc: SqlError) -> JSONResponse:
    logger.exception(f"Get unexpected sql database error: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"message": "Something went wrong. Please notify the maintainer"},
    )


@app.exception_handler(MessageQueueError)
async def mq_exception_handler(request: Request, exc: SqlError) -> JSONResponse:
    logger.exception(f"Get unexpected mq error: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"message": "Something went wrong. Please notify the maintainer"},
    )


@app.exception_handler(Exception)
async def unexpected_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(f"Get unexpected error: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"message": "Something went wrong. Please notify the maintainer"},
    )
