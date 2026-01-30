from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.apis.homes.router import router as homes_router
from app.apis.homeuser.router import router as home_user_router
from app.apis.inventory.router import router as inventory_router
from app.apis.notifications.brokers import RabbitMQBroker
from app.apis.notifications.events_router import \
    router as notification_events_router
from app.apis.notifications.subscriptions_router import \
    router as notification_subscriptions_router
from app.apis.users.router import router as users_router
from app.core.configs.config import settings
from app.core.exception_handlers import register_exception_handlers

rabbit_publisher = RabbitMQBroker(
    amqp_url=settings.RABBITMQ_URL,
    exchange_name=settings.NOTIFICATION_EXCHANGE,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await rabbit_publisher.connect()
    app.state.notification_publisher = rabbit_publisher
    yield
    await rabbit_publisher.close()


app = FastAPI(title="Family-Inventory", lifespan=lifespan)

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
app.include_router(router=notification_events_router, prefix=API_PREFIX)
app.include_router(router=notification_subscriptions_router, prefix=API_PREFIX)

register_exception_handlers(app)


@app.get("/")
async def read_root():
    return {"message": "Hello from Family Inventory API!"}


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        log_level="info",
    )
