import pytest
from sqlalchemy import select

from app.apis.homes.models import Home
from app.apis.notifications.models import InAppNotification, NotificationEvent
from app.apis.notifications.types import NotificationSource
from app.apis.users.models import User


async def _get_auth_user_id(db_session) -> str:
    result = await db_session.execute(
        select(User.id).where(User.email == "auth@example.com")
    )
    return result.scalar_one()


@pytest.mark.asyncio
async def test_inbox_and_unread_count(client, auth_headers, db_session):
    home = Home(name="Notify Home")
    db_session.add(home)
    await db_session.flush()

    auth_user_id = await _get_auth_user_id(db_session)

    event = NotificationEvent(
        source=NotificationSource.INVENTORY.value,
        event_type="inventory.expired",
        subject="Expired Item",
        message="Milk expired",
        recipients={},
    )
    db_session.add(event)
    await db_session.flush()

    notification = InAppNotification(
        event_id=event.id,
        user_id=auth_user_id,
        home_id=home.id,
        subject="Expired Item",
        message="Milk expired",
    )
    db_session.add(notification)
    await db_session.commit()

    res = await client.get("/notifications/inbox", headers=auth_headers)

    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert body[0]["id"] == str(notification.id)

    count = await client.get("/notifications/unread-count", headers=auth_headers)

    assert count.status_code == 200
    assert count.json()["unread"] == 1


@pytest.mark.asyncio
async def test_mark_notification_read(client, auth_headers, db_session):
    home = Home(name="Read Home")
    db_session.add(home)
    await db_session.flush()

    auth_user_id = await _get_auth_user_id(db_session)

    event = NotificationEvent(
        source=NotificationSource.SYSTEM.value,
        event_type="system.notice",
        subject="Notice",
        message="Hello",
        recipients={},
    )
    db_session.add(event)
    await db_session.flush()

    notification = InAppNotification(
        event_id=event.id,
        user_id=auth_user_id,
        home_id=home.id,
        subject="Notice",
        message="Hello",
    )
    db_session.add(notification)
    await db_session.commit()

    res = await client.patch(
        f"/notifications/{notification.id}/read", headers=auth_headers
    )

    assert res.status_code == 204

    updated = await db_session.execute(
        select(InAppNotification.read_at).where(InAppNotification.id == notification.id)
    )
    assert updated.scalar_one() is not None


@pytest.mark.asyncio
async def test_subscription_crud(client, auth_headers):
    home = await client.post(
        "/homes/",
        json={"name": "Subscriptions Home"},
        headers=auth_headers,
    )
    home_id = home.json()["id"]

    payload = {
        "home_id": home_id,
        "topic": "inventory.item.expired",
        "channel": "in_app",
        "enabled": True,
    }

    created = await client.post(
        "/notifications/subscriptions",
        json=payload,
        headers=auth_headers,
    )

    assert created.status_code == 201
    created_body = created.json()
    subscription_id = created_body["id"]
    assert created_body["topic"] == payload["topic"]

    listed = await client.get(
        f"/notifications/subscriptions?home_id={home_id}",
        headers=auth_headers,
    )

    assert listed.status_code == 200
    assert len(listed.json()) == 1

    updated = await client.patch(
        f"/notifications/subscriptions/{subscription_id}",
        json={"enabled": False},
        headers=auth_headers,
    )

    assert updated.status_code == 200
    assert updated.json()["enabled"] is False

    deleted = await client.delete(
        f"/notifications/subscriptions/{subscription_id}",
        headers=auth_headers,
    )

    assert deleted.status_code == 204

    listed_after = await client.get(
        f"/notifications/subscriptions?home_id={home_id}",
        headers=auth_headers,
    )

    assert listed_after.status_code == 200
    assert listed_after.json() == []


@pytest.mark.asyncio
async def test_subscription_duplicate_returns_conflict(client, auth_headers):
    home = await client.post(
        "/homes/",
        json={"name": "Dup Subs Home"},
        headers=auth_headers,
    )
    home_id = home.json()["id"]

    payload = {
        "home_id": home_id,
        "topic": "inventory.item.expired",
        "channel": "in_app",
        "enabled": True,
    }

    first = await client.post(
        "/notifications/subscriptions",
        json=payload,
        headers=auth_headers,
    )
    assert first.status_code == 201

    second = await client.post(
        "/notifications/subscriptions",
        json=payload,
        headers=auth_headers,
    )

    assert second.status_code == 409
    body = second.json()
    assert body["error"] == "SUBSCRIPTION_DUPLICATE"
