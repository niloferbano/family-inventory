from typing import ClassVar

from pydantic_settings import BaseSettings

from app.core.configs.cache_config import CacheConfiguration


class Settings(BaseSettings):
    DATABASE_URL: str = (
        "postgresql+asyncpg://family_user:family_pass@localhost:5432/family_inventory"
    )

    DEBUG: bool = True

    # JWT
    JWT_SECRET_KEY: str = "notset"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    ACTIVATION_TOKEN_EXPIRE_MINUTES: int = 30
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    RELOAD: bool = True  # auto-reload only in dev
    WORKERS: int = 1  # set >1 for production

    # Redis
    CACHE: CacheConfiguration = CacheConfiguration()
    TEST_DATABASE_URL: str = (
        "postgresql+asyncpg://family_test:family_pass@localhost:5433/family_test"
    )

    RABBITMQ_URL: str = "amqp://guest:guest@localhost:5672/"
    NOTIFICATION_EXCHANGE: str = "notifications"
    NOTIFICATION_ROUTING_KEY: str = "notifications.events"
    NOTIFICATION_QUEUE: ClassVar[str] = "notifications.q"
    NOTIFICATION_DLX: ClassVar[str] = "notifications.dlx"
    NOTIFICATION_DLQ: ClassVar[str] = "notifications.dlq"
    NOTIFICATION_ROUTING_KEY: ClassVar[str] = "notifications.#"
    BROKER_MANAGED_RETRIES: bool = False


settings = Settings()
