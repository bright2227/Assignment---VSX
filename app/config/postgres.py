import asyncio
import sys
from asyncio import current_task
from dataclasses import dataclass

from fastapi import FastAPI
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_scoped_session,
    async_sessionmaker,
    create_async_engine,
)

from app.config.config import Settings


@dataclass
class ResourcesManager:
    engine: AsyncEngine
    session_factory: async_scoped_session[AsyncSession]

    @classmethod
    async def initialize(cls, settings: Settings) -> "ResourcesManager":
        engine: AsyncEngine | None = None
        retry_times = 5
        for i in range(1, retry_times + 1):
            try:
                engine = create_async_engine(
                    str(settings.POSTGRES_DSN), pool_pre_ping=True, pool_size=settings.POSTGRES_DB_POOL_SIZE, echo=True
                )
            except OperationalError as e:
                if i == retry_times:
                    raise e
                await asyncio.sleep(3)

        process = await asyncio.create_subprocess_exec("alembic", "upgrade", "head", stderr=sys.stderr, stdout=sys.stdout)
        await process.communicate()
        if process.returncode != 0:
            raise Exception(f"Alembic upgrade fails with code: {process.returncode}")

        assert engine is not None
        session_factory = async_scoped_session(
            async_sessionmaker(
                engine,
                class_=AsyncSession,
                autocommit=False,  # NOTE: autocommit=True is deprecated
                autoflush=False,
                expire_on_commit=False,
            ),
            scopefunc=current_task,
        )
        return cls(engine=engine, session_factory=session_factory)

    async def shutdown(self):
        await self.engine.dispose()


# Usage in FastAPI
async def init(app: FastAPI, settings: Settings):
    app.sql_resources_manager = await ResourcesManager.initialize(settings)  # type: ignore


async def shutdown(app: FastAPI):
    await app.sql_resources_manager.shutdown()  # type: ignore
