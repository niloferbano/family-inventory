"""Uses a real test Redis and PostgreSQL; never sends external email."""

import asyncio
import hashlib
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
import pytest_asyncio
from redis.asyncio import Redis
from sqlalchemy import select

from app.apis.notifications.models import NotificationOutbox
from app.apis.users.exceptions import InvalidActivationToken
from app.apis.users.models import User
from app.apis.users.schema import UserActivationRequest, UserBase
from app.apis.users.user_service import UserService
from app.core.configs.config import settings
from app.iam.token_service import TokenService
from app.jobs import user_cleanup_job


@pytest_asyncio.fixture
async def real_activation_redis(monkeypatch):
    client = Redis.from_url(
        os.getenv("TEST_REDIS_URL", "redis://localhost:6380/0"), decode_responses=True
    )
    keys = set()

    async def save(key, value, ttl=None):
        keys.add(key)
        return await client.set(key, value, ex=ttl)

    class Limiter:
        async def set(self, key, value, **kwargs):
            keys.add(key)
            return await client.set(key, value, **kwargs)

    try:
        await client.ping()
        monkeypatch.setattr("app.iam.token_service.RedisService.set", save)
        monkeypatch.setattr("app.iam.token_service.RedisService.get", client.get)
        monkeypatch.setattr("app.apis.users.user_service.redis_client", Limiter())
        yield client
    finally:
        if keys:
            await client.delete(*keys)
        await client.aclose()


@pytest.mark.asyncio
async def test_real_redis_token_ttl(real_activation_redis):
    token = await TokenService.create_activation_token(
        UserBase(username="ttltest", email="ttl@example.com")
    )
    key = f"activation:{token}"
    assert (
        0
        < await real_activation_redis.ttl(key)
        <= settings.ACTIVATION_TOKEN_EXPIRE_MINUTES * 60
    )
    assert await TokenService.verify_activation_token(token)
    # Accelerate Redis expiry instead of waiting the production TTL.
    await real_activation_redis.pexpire(key, 1)
    await asyncio.sleep(0.03)
    with pytest.raises(ValueError):
        await TokenService.verify_activation_token(token)


@pytest.mark.asyncio
async def test_concurrent_resends_real_cooldown_and_audit(
    client, mock_db, real_activation_redis, monkeypatch
):
    email = f"{uuid4().hex}@example.com"
    async with mock_db.begin() as session:
        session.add(
            User(
                username=uuid4().hex,
                email=email,
                hashed_password="unused",
                is_active=False,
            )
        )
    audit = MagicMock()
    monkeypatch.setattr("app.apis.users.user_service.logger", audit)
    responses = await asyncio.gather(
        *[
            client.post("/users/resend-activation", json={"email": email})
            for _ in range(3)
        ]
    )
    assert all(
        r.status_code == 200 and r.json() == responses[0].json() for r in responses
    )
    async with mock_db.begin() as session:
        assert len((await session.scalars(select(NotificationOutbox))).all()) == 1
    calls = [
        c
        for c in audit.info.call_args_list
        if c.args[0] == "activation_resend_requested"
    ]
    assert len(calls) == 3
    assert sum(c.kwargs["throttled"] for c in calls) == 2
    assert (
        sum(
            c.args[0] == "activation_email_requested" for c in audit.info.call_args_list
        )
        == 1
    )
    key = "activation-resend:" + hashlib.sha256(email.encode()).hexdigest()
    assert (
        0
        < await real_activation_redis.ttl(key)
        <= settings.ACTIVATION_RESEND_COOLDOWN_SECONDS
    )
    await real_activation_redis.pexpire(key, 1)
    await asyncio.sleep(0.03)
    assert (
        await client.post("/users/resend-activation", json={"email": email})
    ).status_code == 200
    async with mock_db.begin() as session:
        assert len((await session.scalars(select(NotificationOutbox))).all()) == 2


@pytest.mark.asyncio
async def test_activation_racing_resend(mock_db, real_activation_redis):
    email = f"{uuid4().hex}@example.com"
    async with mock_db.begin() as session:
        await UserService(session).register_user(
            UserBase(username=uuid4().hex, email=email)
        )
        row = await session.scalar(select(NotificationOutbox))
        token = row.payload["message"].split("/activate/")[1].split()[0]

    async def activate():
        async with mock_db.begin() as session:
            try:
                await UserService(session).create_user(
                    token,
                    UserActivationRequest(
                        password="Secret1", confirm_password="Secret1"
                    ),
                )
                return True
            except InvalidActivationToken:
                return False

    async def resend():
        async with mock_db.begin() as session:
            await UserService(session).resend_activation(email)

    activated, _ = await asyncio.gather(activate(), resend())
    async with mock_db.begin() as session:
        user = await session.scalar(select(User).where(User.email == email))
        rows = (
            await session.scalars(
                select(NotificationOutbox).order_by(NotificationOutbox.created_at)
            )
        ).all()
        assert user.is_active == activated
        assert len(rows) == (1 if activated else 2)
        if not activated:
            new = rows[-1].payload["message"].split("/activate/")[1].split()[0]
            assert new != token
            await UserService(session).create_user(
                new,
                UserActivationRequest(password="Secret1", confirm_password="Secret1"),
            )


@pytest.mark.asyncio
async def test_cleanup_loop_runs_repeatedly_and_logs_after_commit(mock_db, monkeypatch):
    async with mock_db.begin() as session:
        session.add(
            User(
                username="stale",
                email="stale@example.com",
                hashed_password="unused",
                is_active=False,
                created_at=datetime.now(timezone.utc)
                - timedelta(days=settings.UNACTIVATED_USER_RETENTION_DAYS + 1),
            )
        )
    monkeypatch.setattr(user_cleanup_job, "get_db", lambda: mock_db)
    monkeypatch.setattr(user_cleanup_job.sys, "argv", ["cleanup", "--loop"])
    audit = MagicMock()
    monkeypatch.setattr(user_cleanup_job, "logger", audit)
    intervals = []

    async def sleep(interval):
        intervals.append(interval)
        async with mock_db.begin() as session:
            assert (
                await session.scalar(
                    select(User).where(User.email == "stale@example.com")
                )
                is None
            )
        if len(intervals) == 2:
            raise asyncio.CancelledError()

    monkeypatch.setattr(user_cleanup_job, "asyncio", SimpleNamespace(sleep=sleep))
    with pytest.raises(asyncio.CancelledError):
        await user_cleanup_job.main()
    assert intervals == [settings.USER_CLEANUP_INTERVAL_SECONDS] * 2
    audit.info.assert_any_call("unactivated_users_cleaned", count=1)
    audit.info.assert_any_call("unactivated_users_cleaned", count=0)
