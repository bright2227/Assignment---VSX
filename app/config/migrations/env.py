import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, engine_from_config, pool, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config.config import Settings
from app.domain.tasks import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config
settings = Settings()  # type: ignore
config.set_main_option("sqlalchemy.url", str(settings.POSTGRES_DSN))

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


# no offline mode for now
def do_run_migrations(connection: Connection):
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        connection.execute(text(f"SELECT pg_advisory_xact_lock({hash('alembic')});"))
        context.run_migrations()


async def run_migrations_online():
    """Run migrations in 'online' mode.
    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    engine_config = config.get_section(config.config_ini_section)
    assert engine_config is not None
    engine = AsyncEngine(
        engine_from_config(
            engine_config,
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
            future=True,
        )
    )
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)


asyncio.run(main=run_migrations_online())
