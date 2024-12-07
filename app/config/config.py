from typing import Optional

from pydantic import AmqpDsn, PostgresDsn, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Fastapi settings."""

    model_config = SettingsConfigDict(case_sensitive=True)

    LOG_LEVEL: str = "DEBUG"

    # enable this if you want to build a new db in your local
    POSTGRES_HOST: str
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_DSN: PostgresDsn | None = None
    POSTGRES_DB_POOL_SIZE: int = 10

    @field_validator("POSTGRES_DSN", mode="before")
    @classmethod
    def assemble_db_connection(cls, v: Optional[str], values: ValidationInfo) -> PostgresDsn:
        return PostgresDsn.build(
            scheme="postgresql+asyncpg",
            username=values.data.get("POSTGRES_USER"),
            password=values.data.get("POSTGRES_PASSWORD"),
            host=values.data.get("POSTGRES_HOST"),
            port=values.data.get("POSTGRES_PORT"),
            path=f"{values.data.get('POSTGRES_DB') or ''}",
        )

    # enable this if you want to build a new db in your local
    RABBITMQ_HOST: str
    RABBITMQ_PORT: int = 5672
    RABBITMQ_DEFAULT_USER: str
    RABBITMQ_DEFAULT_PASS: str
    RABBITMQ_DSN: AmqpDsn | None = None

    @field_validator("RABBITMQ_DSN", mode="before")
    @classmethod
    def assemble_ampq_connection(cls, v: Optional[str], values: ValidationInfo) -> AmqpDsn:
        return AmqpDsn.build(
            scheme="amqp",
            username=values.data.get("RABBITMQ_DEFAULT_USER"),
            password=values.data.get("RABBITMQ_DEFAULT_PASS"),
            host=values.data.get("RABBITMQ_HOST"),  # type: ignore
            port=values.data.get("RABBITMQ_PORT"),
        )
