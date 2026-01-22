from fastapi import APIRouter, Depends, Request

from app.apis.notifications.schema import (NotificationRequest,
                                           NotificationResponse)
from app.apis.notifications.service import NotificationService
from app.core.database.session import get_db

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.post("/", response_model=NotificationResponse)
async def send_notification(
    payload: NotificationRequest,
    request: Request,
    db_manager=Depends(get_db),
):
    async with db_manager.begin() as session:
        service = NotificationService(session=session)
        return await service.send(payload)
