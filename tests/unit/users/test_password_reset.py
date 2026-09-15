import asyncio
import hashlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import urlsplit

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.apis.notifications.models import NotificationOutbox
from app.apis.users.auth_service import AuthService
from app.apis.users.exceptions import InvalidResetToken
from app.apis.users.models import User
from app.iam.password_service import PasswordService


@pytest_asyncio.fixture
async def account(mock_db):
    async with mock_db.begin() as session:
        user = User(
            username="resetuser",
            email="reset@example.com",
            is_active=True,
            hashed_password=PasswordService.hash("Oldpass1"),
        )
        session.add(user)
        await session.flush()
        return user.id


async def request_token(client, mock_db):
    response = await client.post(
        "/users/password-reset/request", json={"email": "reset@example.com"}
    )
    assert response.status_code == 200
    async with mock_db.begin() as session:
        row = await session.scalar(
            select(NotificationOutbox)
            .where(NotificationOutbox.topic == "users.password_reset.requested")
            .order_by(NotificationOutbox.created_at.desc())
        )
        link = next(
            line
            for line in row.payload["message"].splitlines()
            if "/reset-password/" in line
        )
        return urlsplit(link).path.rsplit("/", 1)[1]


async def confirm(client, token, password="Newpass2"):
    return await client.post(
        "/users/password-reset/confirm",
        json={"token": token, "password": password, "confirm_password": password},
    )


@pytest.mark.asyncio
async def test_valid_reset_and_reused_token(client, mock_db, account):
    token = await request_token(client, mock_db)
    async with mock_db.begin() as session:
        user = await session.get(User, account)
        assert user.password_reset_hash == hashlib.sha256(token.encode()).hexdigest()
        assert user.password_reset_expires_at > datetime.now(timezone.utc)
    assert (await confirm(client, token)).status_code == 200
    assert (await confirm(client, token)).status_code == 400
    async with mock_db.begin() as session:
        user = await session.get(User, account)
        assert user.password_reset_hash is None
        assert PasswordService.verify("Newpass2", user.hashed_password)
        assert not PasswordService.verify("Oldpass1", user.hashed_password)


@pytest.mark.asyncio
async def test_expired_token(client, mock_db, account):
    token = await request_token(client, mock_db)
    async with mock_db.begin() as session:
        user = await session.get(User, account)
        user.password_reset_expires_at = datetime.now(timezone.utc) - timedelta(
            seconds=1
        )
    assert (await confirm(client, token)).status_code == 400


@pytest.mark.asyncio
async def test_invalid_token(client, account):
    assert (await confirm(client, "not-a-real-token")).status_code == 400


@pytest.mark.asyncio
async def test_multiple_requests_invalidate_previous(client, mock_db, account):
    first = await request_token(client, mock_db)
    second = await request_token(client, mock_db)
    assert first != second
    assert (await confirm(client, first)).status_code == 400
    assert (await confirm(client, second)).status_code == 200


@pytest.mark.asyncio
async def test_generic_response_for_unknown_and_inactive(client, mock_db, account):
    known = await client.post(
        "/users/password-reset/request", json={"email": "reset@example.com"}
    )
    unknown = await client.post(
        "/users/password-reset/request", json={"email": "unknown@example.com"}
    )
    async with mock_db.begin() as session:
        user = await session.get(User, account)
        user.is_active = False
    inactive = await client.post(
        "/users/password-reset/request", json={"email": "reset@example.com"}
    )
    assert known.status_code == unknown.status_code == inactive.status_code == 200
    assert known.json() == unknown.json() == inactive.json()
    async with mock_db.begin() as session:
        assert len((await session.scalars(select(NotificationOutbox))).all()) == 1


@pytest.mark.asyncio
async def test_reset_rollback_preserves_token(client, mock_db, account):
    token = await request_token(client, mock_db)
    with pytest.raises(RuntimeError):
        async with mock_db.begin() as session:
            await AuthService(session).reset_password(token, "Newpass2")
            raise RuntimeError("rollback")
    assert (await confirm(client, token)).status_code == 200


@pytest.mark.asyncio
async def test_concurrent_reset_only_one_succeeds(client, mock_db, account):
    token = await request_token(client, mock_db)

    async def attempt():
        try:
            async with mock_db.begin() as session:
                await AuthService(session).reset_password(token, "Newpass2")
            return True
        except InvalidResetToken:
            return False

    assert sorted(await asyncio.gather(attempt(), attempt())) == [False, True]


@pytest.mark.asyncio
async def test_password_validation_preserves_token(client, mock_db, account):
    token = await request_token(client, mock_db)
    response = await client.post(
        "/users/password-reset/confirm",
        json={"token": token, "password": "Newpass2", "confirm_password": "Different3"},
    )
    assert response.status_code == 422
    assert (await confirm(client, token)).status_code == 200


@pytest.mark.asyncio
async def test_reset_email_through_worker(client, mock_db, account, monkeypatch):
    import json

    from app.apis.notifications.models import NotificationDelivery
    from app.apis.notifications.worker import channels, consumer
    from app.apis.notifications.worker.sweeper import sweep_outbox_once
    from app.core.configs.config import settings

    token = await request_token(client, mock_db)
    broker = SimpleNamespace(publish=AsyncMock())
    assert (
        await sweep_outbox_once(sessionmaker=mock_db.sessionmaker, broker=broker) == 1
    )
    envelope = broker.publish.call_args.args[0]
    monkeypatch.setattr(consumer, "_build_realtime_service", lambda: None)
    smtp = MagicMock()
    monkeypatch.setattr(channels.smtplib, "SMTP", MagicMock(return_value=smtp))
    monkeypatch.setattr(settings.SMTP, "use_ssl", False)
    worker = consumer.NotificationWorker(
        cfg=consumer.WorkerConfig(
            amqp_url="unused", exchange_name="test", queue_name="test", bindings=[]
        ),
        sessionmaker=mock_db.sessionmaker,
    )
    msg = SimpleNamespace(
        body=json.dumps(envelope.payload).encode(),
        headers=envelope.headers,
        routing_key=envelope.topic,
        message_id=str(envelope.payload["event_id"]),
        correlation_id=None,
        content_type="application/json",
        ack=AsyncMock(),
        reject=AsyncMock(),
    )
    await worker.on_message(msg)
    msg.ack.assert_awaited_once()
    msg.reject.assert_not_awaited()
    email = smtp.__enter__.return_value.send_message.call_args.args[0]
    assert email["To"] == "reset@example.com"
    assert (
        "/reset-password/" + token
        in email.get_body(preferencelist=("plain",)).get_content()
    )
    async with mock_db.begin() as session:
        delivery = await session.scalar(select(NotificationDelivery))
        assert delivery.status.value == "sent"
