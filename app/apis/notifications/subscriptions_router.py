from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.apis.notifications.schema import (SubscriptionCreate, SubscriptionOut,
                                           SubscriptionUpdate)
from app.apis.notifications.service import NotificationPreferencesService
from app.apis.users.models import User
from app.core.database.session import get_db
from app.iam.dependencies import get_current_user

router = APIRouter(prefix="/notifications/subscriptions", tags=["subscriptions"])


@router.get("", response_model=list[SubscriptionOut])
async def list_my_subscriptions(
    home_id: UUID | None = None,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = NotificationPreferencesService(session)
    return await svc.list_my_subscriptions(user_id=current_user.id, home_id=home_id)


@router.post("", response_model=SubscriptionOut, status_code=status.HTTP_201_CREATED)
async def create_subscription(
    req: SubscriptionCreate,
    db_manager: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    async with db_manager.begin() as session:
        svc = NotificationPreferencesService(session)
        return await svc.create_subscription(user_id=current_user.id, req=req)


@router.patch("/{subscription_id}", response_model=SubscriptionOut)
async def update_subscription(
    subscription_id: UUID,
    req: SubscriptionUpdate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = NotificationPreferencesService(session)
    return await svc.update_subscription(
        user_id=current_user.id, subscription_id=subscription_id, req=req
    )


@router.delete("/{subscription_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_subscription(
    subscription_id: UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = NotificationPreferencesService(session)
    await svc.delete_subscription(
        user_id=current_user.id, subscription_id=subscription_id
    )
