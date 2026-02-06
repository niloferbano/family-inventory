from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, WebSocket, status
from redis.asyncio import Redis
from redis.asyncio.connection import ConnectionPool

from app.apis.notifications.schema import (InAppNotificationOut,
                                           SubscriptionCreateRequest,
                                           SubscriptionOut, SubscriptionUpdate)
from app.apis.notifications.services.inbox import NotificationInboxService
from app.apis.notifications.services.subscription import \
    NotificationSubscriptionsService
from app.apis.users.models import User
from app.core.database.base import HomeId
from app.core.database.session import get_db
from app.core.logging import get_logger
from app.core.redis.client import redis_client
from app.iam.dependencies import get_current_user
from app.iam.websocket_auth import get_current_user_ws

logger = get_logger(__name__)

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("/inbox", response_model=list[InAppNotificationOut])
async def list_inbox(
    home_id: HomeId | None = Query(default=None),
    unread_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db_manager=Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    async with db_manager.begin() as session:
        svc = NotificationInboxService(session)
        return await svc.list_inbox(
            user_id=current_user.id,
            home_id=home_id,
            unread_only=unread_only,
            limit=limit,
            offset=offset,
        )


@router.get("/unread-count", response_model=dict)
async def unread_count(
    home_id: HomeId | None = Query(default=None),
    db_manager=Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    async with db_manager.begin() as session:
        svc = NotificationInboxService(session)
        count = await svc.unread_count(user_id=current_user.id, home_id=home_id)
        return {"unread": count}


@router.patch("/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read(
    notification_id: UUID,
    db_manager=Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    async with db_manager.begin() as session:
        svc = NotificationInboxService(session)
        await svc.mark_read(user_id=current_user.id, notification_id=notification_id)
        return


@router.get(
    "/subscriptions", response_model=list[SubscriptionOut], tags=["subscriptions"]
)
async def list_my_subscriptions(
    home_id: UUID | None = None,
    db_manager=Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    async with db_manager.begin() as session:
        svc = NotificationSubscriptionsService(session)
        return await svc.list_my_subscriptions(user_id=current_user.id, home_id=home_id)


@router.post(
    "/subscriptions",
    response_model=SubscriptionOut,
    status_code=status.HTTP_201_CREATED,
    tags=["subscriptions"],
)
async def create_subscription(
    req: SubscriptionCreateRequest,
    db_manager=Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    async with db_manager.begin() as session:
        svc = NotificationSubscriptionsService(session)
        return await svc.create_subscription(user_id=current_user.id, req=req)


@router.patch(
    "/subscriptions/{subscription_id}",
    response_model=SubscriptionOut,
    tags=["subscriptions"],
)
async def update_subscription(
    subscription_id: UUID,
    req: SubscriptionUpdate,
    db_manager=Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    async with db_manager.begin() as session:
        svc = NotificationSubscriptionsService(session)
        return await svc.update_subscription(
            user_id=current_user.id,
            subscription_id=subscription_id,
            req=req,
        )


@router.delete(
    "/subscriptions/{subscription_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["subscriptions"],
)
async def delete_subscription(
    subscription_id: UUID,
    db_manager=Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    async with db_manager.begin() as session:
        svc = NotificationSubscriptionsService(session)
        await svc.delete_subscription(
            user_id=current_user.id, subscription_id=subscription_id
        )


def _user_channel(user_id) -> str:
    return f"notifications.in_app.{user_id}"


def _normalize_redis(obj: Any) -> Redis | None:
    """Return a Redis client instance that supports `.pubsub()`.

    We sometimes store a `ConnectionPool` in `app.state.redis` which does not expose
    `.pubsub()`. In that case we wrap it with `Redis(connection_pool=pool)`.
    """
    if obj is None:
        return None
    # If app.state.redis is a connection pool, wrap it.
    if isinstance(obj, ConnectionPool):
        return Redis(connection_pool=obj)
    # If it's already a Redis client, just return it.
    if hasattr(obj, "pubsub"):
        return obj  # type: ignore[return-value]
    return None


@router.websocket("/ws")
@router.websocket("/ws/inbox")
async def ws_inbox(websocket: WebSocket, db_manager=Depends(get_db)):
    """
    Authenticated WS stream for in-app notifications.

    Server pushes Redis pubsub messages on channel:
      notifications.inapp.<user_id>

    Client should still fetch /notifications/inbox for full data.
    """
    await websocket.accept()
    pubsub = None
    channel = None

    # --- DB session for auth (and optional future commands) ---
    # get_db() in your project returns DBManager sometimes; keep this consistent.

    try:
        async with db_manager.begin() as session:
            user = await get_current_user_ws(websocket, session)
            if not user:
                return
            user_id = user.id

        # --- Redis ---
        # Prefer app.state.redis, but fall back to the module-level redis_client.
        redis_obj = getattr(websocket.app.state, "redis", None) or redis_client
        redis = _normalize_redis(redis_obj)

        if redis is None:
            # Degrade gracefully: keep socket open but no realtime.
            await websocket.send_json(
                {
                    "type": "warning",
                    "message": "Realtime disabled (Redis not configured)",
                }
            )
            # Keep alive until client disconnects
            while True:
                await websocket.receive_text()

        pubsub = redis.pubsub()
        channel = _user_channel(user_id)
        await pubsub.subscribe(channel)

        async def _pump_redis() -> None:
            # redis-py pubsub listen yields dicts
            async for msg in pubsub.listen():
                if msg is None:
                    continue
                if msg.get("type") != "message":
                    continue
                data = msg.get("data")
                # redis returns bytes sometimes
                if isinstance(data, (bytes, bytearray)):
                    data = data.decode("utf-8", errors="replace")
                try:
                    payload = json.loads(data) if isinstance(data, str) else data
                except Exception:
                    payload = {"type": "notification.raw", "data": data}
                await websocket.send_json(payload)

        async def _pump_client() -> None:
            # Optional: handle pings / future commands
            while True:
                text = await websocket.receive_text()
                if text == "ping":
                    await websocket.send_text("pong")

        redis_task = asyncio.create_task(_pump_redis())
        client_task = asyncio.create_task(_pump_client())

        done, pending = await asyncio.wait(
            {redis_task, client_task},
            return_when=asyncio.FIRST_EXCEPTION,
        )
        for t in pending:
            t.cancel()
        for t in done:
            exc = t.exception()
            if exc:
                raise exc

    finally:
        # best-effort cleanup
        try:
            if pubsub is not None:
                try:
                    if channel:
                        await pubsub.unsubscribe(channel)
                except Exception:
                    pass
                try:
                    await pubsub.close()
                except Exception:
                    pass
        except Exception:
            pass
