from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.configs.cache_config import CacheConfiguration
from app.core.configs.smtp_config import SMTPSettings


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
        extra="ignore",
    )
    DATABASE_URL: str = (
        "postgresql+asyncpg://family_user:family_pass@localhost:5432/family_inventory"
    )

    DEBUG: bool = True

    SMTP: SMTPSettings = SMTPSettings()

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
    NOTIFICATION_QUEUE: str = "notifications.q"
    NOTIFICATION_DLX: str = "notifications.dlx"
    NOTIFICATION_DLQ: str = "notifications.dlq"
    NOTIFICATION_DLQ_ROUTING_KEY: str = "dlq"

    # consume bindings (comma-separated)
    NOTIFICATION_BINDINGS: str = "inventory.item.*"

    # broker-managed retry infra
    BROKER_MANAGED_RETRIES: bool = False
    NOTIFICATION_RETRY_EXCHANGE: str = "notifications.retry"
    NOTIFICATION_RETRY_ROUTING_KEY_30S: str = "retry.30s"
    NOTIFICATION_RETRY_RETURN_TOPIC: str = "inventory.item.retry"

    def notification_bindings_list(self) -> list[str]:
        return [b.strip() for b in self.NOTIFICATION_BINDINGS.split(",") if b.strip()]


settings = Settings()
