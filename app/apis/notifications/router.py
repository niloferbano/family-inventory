from __future__ import annotations

from uuid import UUID

from fastapi import (APIRouter, Depends, Query, WebSocket, WebSocketDisconnect,
                     status)
from jose import ExpiredSignatureError, JWTError

from app.apis.notifications.schema import (InAppNotificationOut,
                                           NotificationRequest,
                                           NotificationResponse)
from app.apis.notifications.service import (NotificationInboxService,
                                            NotificationRealtimeService,
                                            NotificationService)
from app.apis.users.models import User
from app.apis.users.repository import UserRepository
from app.core.database.base import HomeId, UserId
from app.core.database.session import get_db
from app.core.logging import get_logger
from app.core.redis.client import redis_client
from app.iam.dependencies import get_current_user
from app.iam.token_service import TokenService

logger = get_logger(__name__)

router = APIRouter(prefix="/notifications", tags=["Notifications"])


def _extract_ws_token(websocket: WebSocket) -> str | None:
    token = websocket.query_params.get("token")
    if token:
        return token
    auth = websocket.headers.get("authorization")
    if not auth:
        return None
    parts = auth.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None


@router.post("/", response_model=NotificationResponse)
async def send_notification(
    payload: NotificationRequest,
    session=Depends(get_db),
):
    service = NotificationService(session=session)
    return await service.send(payload)


@router.get("/inbox", response_model=list[InAppNotificationOut])
async def list_inbox(
    home_id: HomeId | None = Query(default=None),
    unread_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session=Depends(get_db),
    current_user: User = Depends(get_current_user),
):
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
    session=Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = NotificationInboxService(session)
    count = await svc.unread_count(user_id=current_user.id, home_id=home_id)
    return {"unread": count}


@router.patch("/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read(
    notification_id: UUID,
    session=Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = NotificationInboxService(session)
    await svc.mark_read(user_id=current_user.id, notification_id=notification_id)
    return


@router.websocket("/ws")
async def notifications_ws(
    websocket: WebSocket,
    db_manager=Depends(get_db),
):
    token = _extract_ws_token(websocket)
    if not token:
        await websocket.close(code=1008)
        return

    try:
        payload = TokenService.decode_token(token)
    except (ExpiredSignatureError, JWTError):
        await websocket.close(code=1008)
        return

    async with db_manager.begin() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(UserId(UUID(payload.user_id)))
        if not user or not user.is_active:
            await websocket.close(code=1008)
            return
        user_id = user.id

    await websocket.accept()

    channel = f"{NotificationRealtimeService.CHANNEL_PREFIX}{user_id}"
    pubsub = redis_client.pubsub()

    try:
        await pubsub.subscribe(channel)
    except Exception:
        logger.exception("WS subscribe failed user_id=%s", user_id)
        await websocket.close(code=1011)
        await pubsub.close()
        return

    try:
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            data = message.get("data")
            if data is None:
                continue
            await websocket.send_text(str(data))
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("WS stream failed user_id=%s", user_id)
    finally:
        try:
            await pubsub.unsubscribe(channel)
        finally:
            await pubsub.close()
