import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.apis.notifications.models import NotificationOutbox
from app.apis.users.exceptions import InvalidActivationToken
from app.apis.users.models import User
from app.apis.users.schema import (
    ResendActivationResponse,
    UserActivationRequest,
    UserBase,
)
from app.apis.users.user_service import UserService
from app.core.configs.config import settings
from app.iam.token_service import TokenService
from app.jobs.user_cleanup_job import cleanup_users


@pytest.fixture
def activation_cache(monkeypatch):
    values = {}

    async def save(key, value, ttl=None):
        values[key] = value
        assert ttl == settings.ACTIVATION_TOKEN_EXPIRE_MINUTES * 60

    async def get(key):
        return values.get(key)

    monkeypatch.setattr("app.iam.token_service.RedisService.set", save)
    monkeypatch.setattr("app.iam.token_service.RedisService.get", get)
    monkeypatch.setattr(
        "app.apis.users.user_service.redis_client.set", AsyncMock(return_value=True)
    )
    return values


@pytest.mark.asyncio
async def test_resend_replaces_token_and_new_token_activates(mock_db, activation_cache):
    async with mock_db.begin() as session:
        await UserService(session).register_user(
            UserBase(username="resend", email="resend@example.com")
        )
    old = next(iter(activation_cache)).split(":", 1)[1]
    async with mock_db.begin() as session:
        await UserService(session).resend_activation("resend@example.com")
    new = list(activation_cache)[-1].split(":", 1)[1]
    assert new != old
    password = UserActivationRequest(password="Secret1", confirm_password="Secret1")
    async with mock_db.begin() as session:
        with pytest.raises(InvalidActivationToken):
            await UserService(session).create_user(old, password)
        user = await UserService(session).create_user(new, password)
        assert user.is_active
    async with mock_db.begin() as session:
        with pytest.raises(InvalidActivationToken):
            await UserService(session).create_user(new, password)


@pytest.mark.asyncio
async def test_expired_token_returns_400(client, mock_db, activation_cache):
    async with mock_db.begin() as session:
        await UserService(session).register_user(
            UserBase(username="expired", email="expired@example.com")
        )
        user = await session.scalar(
            select(User).where(User.email == "expired@example.com")
        )
        user.activation_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    token = next(iter(activation_cache)).split(":", 1)[1]
    response = await client.post(
        f"/users/activate/{token}",
        json={"password": "Secret1", "confirm_password": "Secret1"},
    )
    assert response.status_code == 400
    activation_cache.clear()
    with pytest.raises(ValueError):
        await TokenService.verify_activation_token(token)


@pytest.mark.asyncio
async def test_resend_generic_and_throttled(
    client, mock_db, activation_cache, monkeypatch
):
    async with mock_db.begin() as session:
        session.add(
            User(
                username="active",
                email="active@example.com",
                hashed_password="unused",
                is_active=True,
            )
        )
        session.add(
            User(
                username="inactive",
                email="inactive@example.com",
                hashed_password="unused",
                is_active=False,
            )
        )
    responses = []
    for email in ["active@example.com", "unknown@example.com"]:
        responses.append(
            await client.post("/users/resend-activation", json={"email": email})
        )
    throttle = AsyncMock(return_value=False)
    monkeypatch.setattr("app.apis.users.user_service.redis_client.set", throttle)
    responses.append(
        await client.post(
            "/users/resend-activation", json={"email": "inactive@example.com"}
        )
    )
    assert all(
        r.status_code == 200 and r.json() == ResendActivationResponse().model_dump()
        for r in responses
    )
    assert throttle.call_args.kwargs == {
        "nx": True,
        "ex": settings.ACTIVATION_RESEND_COOLDOWN_SECONDS,
    }
    async with mock_db.begin() as session:
        assert (await session.scalars(select(NotificationOutbox))).all() == []


@pytest.mark.asyncio
async def test_cleanup_retains_active_recent_and_valid_link_users(mock_db):
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=settings.UNACTIVATED_USER_RETENTION_DAYS + 1)
    async with mock_db.begin() as session:
        for name, active, created, expires in [
            ("expired", False, old, old),
            ("legacy", False, old, None),
            ("active", True, old, old),
            ("recent", False, now, now),
            ("valid", False, old, now + timedelta(minutes=10)),
        ]:
            session.add(
                User(
                    username=name,
                    email=f"{name}@example.com",
                    hashed_password="unused",
                    is_active=active,
                    created_at=created,
                    activation_expires_at=expires,
                )
            )
    async with mock_db.begin() as session:
        assert await cleanup_users(session, now=now) == 2
    async with mock_db.begin() as session:
        assert set((await session.scalars(select(User.username))).all()) == {
            "active",
            "recent",
            "valid",
        }


@pytest.mark.asyncio
async def test_get_activate_key_valid(client, mock_db, activation_cache):
    async with mock_db.begin() as session:
        await UserService(session).register_user(
            UserBase(username="getvalid", email="getvalid@example.com")
        )
    token = next(iter(activation_cache)).split(":", 1)[1]

    # Test GET pre-check on valid token
    response = await client.get(f"/users/activate/{token}")
    assert response.status_code == 200
    assert response.json() == {"message": "Activation key is valid"}


@pytest.mark.asyncio
async def test_get_activate_key_already_active(client, mock_db, activation_cache):
    async with mock_db.begin() as session:
        session.add(
            User(
                username="alreadyactive",
                email="activeuser@example.com",
                hashed_password="hashed",
                is_active=True,
                activation_token_hash=hashlib.sha256(
                    b"somekeythatmatcheshash"
                ).hexdigest(),
            )
        )

    # Test GET pre-check when the user is already active
    response = await client.get("/users/activate/somekeythatmatcheshash")
    assert response.status_code == 400
    assert response.json()["detail"] == "ALREADY_ACTIVE"


@pytest.mark.asyncio
async def test_get_activate_key_expired_or_invalid(client, mock_db, activation_cache):
    # Test GET pre-check on a completely non-existent or invalid key
    response = await client.get("/users/activate/nonexistentkey123")
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid or expired activation link"
