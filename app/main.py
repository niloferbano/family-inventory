import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis
from uvicorn.config import LOGGING_CONFIG

from app.apis.homes.router import router as homes_router
from app.apis.homeuser.router import router as home_user_router
from app.apis.inventory.router import router as inventory_router
from app.apis.notifications.brokers import RabbitMQBroker
from app.apis.notifications.router import router as notification_router
from app.apis.users.router import router as users_router
from app.core.configs.config import settings
from app.core.exception_handlers import register_exception_handlers
from app.core.logging import get_logger

rabbit_publisher = RabbitMQBroker(
    amqp_url=settings.RABBITMQ_URL,
    exchange_name=settings.NOTIFICATION_EXCHANGE,
)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _silence_websocket_logs()
    await rabbit_publisher.connect()
    app.state.notification_publisher = rabbit_publisher
    app.state.redis = Redis.from_url(settings.CACHE.url, decode_responses=True)
    logger.info("WebSocket notifications enabled")
    yield
    await rabbit_publisher.close()
    await app.state.redis.close()


def _silence_websocket_logs() -> None:
    class _WebSocketNoiseFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            msg = record.getMessage()
            if not msg:
                return True
            lowered = msg.lower()
            if "websocket" in lowered:
                return False
            if "connection open" in lowered or "connection closed" in lowered:
                return False
            return True

    noise_filter = _WebSocketNoiseFilter()
    for name in (
        "uvicorn.access",
        "uvicorn.error",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.websockets_impl",
        "uvicorn.protocols.websockets.wsproto_impl",
        "websockets",
        "websockets.server",
        "websockets.protocol",
    ):
        logger = logging.getLogger(name)
        logger.addFilter(noise_filter)
        if name == "uvicorn.access":
            logger.disabled = True


app = FastAPI(
    title="Family-Inventory",
    lifespan=lifespan,
    swagger_ui_oauth2_redirect_url="/oauth2-redirect",
    swagger_ui_init_oauth={
        "usePkceWithAuthorizationCodeGrant": True,
        "clientId": "family-inventory-client-id",
        "appName": "Family Inventory API",
    },
)


ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
API_PREFIX = "/api/v1"
app.include_router(router=users_router, prefix=API_PREFIX)
app.include_router(router=homes_router, prefix=API_PREFIX)
app.include_router(router=home_user_router, prefix=API_PREFIX)
app.include_router(router=inventory_router, prefix=API_PREFIX)
app.include_router(router=notification_router, prefix=API_PREFIX)


register_exception_handlers(app)


@app.get("/")
async def read_root():
    return {"message": "Hello from Family Inventory API!"}


def make_uvicorn_log_config():
    cfg = dict(LOGGING_CONFIG)  # shallow copy is fine; we’ll only tweak dict values
    cfg["loggers"] = dict(cfg.get("loggers", {}))

    # Disable HTTP access log
    cfg["loggers"]["uvicorn.access"] = {
        "handlers": ["access"],
        "level": "WARNING",
        "propagate": False,
    }

    # Silence websocket connect/disconnect noise
    cfg["loggers"]["uvicorn.error"] = {
        "handlers": ["default"],
        "level": "WARNING",
        "propagate": False,
    }
    for logger_name in (
        "websockets",
        "websockets.server",
        "websockets.protocol",
    ):
        cfg["loggers"][logger_name] = {
            "handlers": [],
            "level": "CRITICAL",
            "propagate": False,
        }

    return cfg


if __name__ == "__main__":
    logging.getLogger("websockets").setLevel(logging.WARNING)
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        workers=settings.WORKERS,
        proxy_headers=True,
        forwarded_allow_ips="*",
        log_level="info",  # keep your app logs
        access_log=False,  # still good to keep
        log_config=make_uvicorn_log_config(),
    )
