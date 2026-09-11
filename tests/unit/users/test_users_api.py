import pytest
from sqlalchemy import select

from app.apis.users.models import User
from app.apis.users.schema import UserBase
from app.iam.password_service import PasswordService
from app.iam.token_service import TokenService
from app.iam.types import ActivationKey


@pytest.mark.asyncio
async def test_me_returns_current_user(client, auth_headers):
    res = await client.get("/users/me", headers=auth_headers)

    assert res.status_code == 200
    body = res.json()
    assert body["email"] == "auth@example.com"


@pytest.mark.asyncio
async def test_register_user_queues_activation_email(client, db_session, monkeypatch):
    async def fake_create_activation_token(cls, user_data: UserBase):
        return ActivationKey("a" * 32)

    monkeypatch.setattr(
        TokenService,
        "create_activation_token",
        classmethod(fake_create_activation_token),
    )

    res = await client.post(
        "/users/register",
        json={"username": "newuser", "email": "newuser@example.com"},
    )

    assert res.status_code == 200
    body = res.json()
    assert "activation_key" not in body
    user = await db_session.scalar(
        select(User).where(User.email == "newuser@example.com")
    )
    assert user is not None and not user.is_active
    from app.apis.notifications.models import NotificationOutbox
    from app.apis.notifications.types import NotificationChannel
    from app.apis.notifications.worker.handlers import prepare_event_deliveries

    outbox = await db_session.scalar(
        select(NotificationOutbox).where(
            NotificationOutbox.payload["user_id"].astext == str(user.id)
        )
    )
    assert outbox.status == "PENDING"
    assert outbox.topic == "users.activation.requested"
    assert "/activate/" + "a" * 32 in outbox.payload["message"]
    batch = await prepare_event_deliveries(
        db_session,
        topic=outbox.topic,
        payload=outbox.payload,
        headers=outbox.headers,
        worker_id="activation-test",
    )
    assert len(batch.tasks) == 1
    assert batch.tasks[0].channel == NotificationChannel.EMAIL
    assert batch.tasks[0].recipient == user.email
    again = await prepare_event_deliveries(
        db_session,
        topic=outbox.topic,
        payload=outbox.payload,
        headers=outbox.headers,
        worker_id="activation-test-2",
    )
    assert not again.tasks


@pytest.mark.asyncio
async def test_register_duplicate_email_returns_409(client, db_session):
    user = User(
        username="existing",
        email="dup@example.com",
        hashed_password="hashed",
        is_active=True,
        is_admin=False,
    )
    db_session.add(user)
    await db_session.commit()

    res = await client.post(
        "/users/register",
        json={"username": "newuser", "email": "dup@example.com"},
    )

    assert res.status_code == 409
    body = res.json()
    assert body["detail"] == "User already exists."


@pytest.mark.asyncio
async def test_activate_user_creates_account(client, db_session, monkeypatch):
    db_session.add(
        User(
            username="activated",
            email="activated@example.com",
            hashed_password="unused",
            is_active=False,
        )
    )
    await db_session.commit()

    async def fake_verify_activation_token(cls, token: ActivationKey):
        return UserBase(
            username="activated",
            email="activated@example.com",
        ).model_dump_json()

    monkeypatch.setattr(
        TokenService,
        "verify_activation_token",
        classmethod(fake_verify_activation_token),
    )

    res = await client.post(
        f"/users/activate/{'a' * 32}",
        json={"password": "Secret1", "confirm_password": "Secret1"},
    )

    assert res.status_code == 201
    body = res.json()
    assert body["message"] == "User activated successfully"

    created = await db_session.execute(
        select(User.id).where(User.email == "activated@example.com")
    )
    assert created.scalar_one() is not None


@pytest.mark.asyncio
async def test_login_returns_token(client, db_session):
    password = "Secret1"
    user = User(
        username="loginuser",
        email="login@example.com",
        hashed_password=PasswordService.hash(password),
        is_active=True,
        is_admin=False,
    )
    db_session.add(user)
    await db_session.commit()

    res = await client.post(
        "/users/login",
        json={"email": "login@example.com", "password": password},
    )

    assert res.status_code == 200
    body = res.json()
    assert isinstance(body.get("access_token"), str)


@pytest.mark.asyncio
async def test_login_invalid_returns_400(client, db_session):
    password = "Secret1"
    user = User(
        username="loginuser2",
        email="login2@example.com",
        hashed_password=PasswordService.hash(password),
        is_active=True,
        is_admin=False,
    )
    db_session.add(user)
    await db_session.commit()

    res = await client.post(
        "/users/login",
        json={"email": "login2@example.com", "password": "Wrong1"},
    )

    assert res.status_code == 400
    body = res.json()
    assert body["detail"] == "Invalid credentials"


@pytest.mark.asyncio
async def test_inactive_user_cannot_login(client, db_session):
    db_session.add(
        User(
            username="pending",
            email="pending@example.com",
            hashed_password=PasswordService.hash("Secret1"),
            is_active=False,
        )
    )
    await db_session.commit()
    res = await client.post(
        "/users/login", json={"email": "pending@example.com", "password": "Secret1"}
    )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_invalid_activation_returns_400(client, monkeypatch):
    from unittest.mock import AsyncMock

    monkeypatch.setattr(
        TokenService,
        "verify_activation_token",
        AsyncMock(side_effect=ValueError("expired")),
    )
    res = await client.post(
        f"/users/activate/{'z' * 32}",
        json={"password": "Secret1", "confirm_password": "Secret1"},
    )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_activation_outbox_through_consumer_and_email_sender(
    client, mock_db, monkeypatch
):
    import json
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock

    from app.apis.notifications.models import NotificationDelivery
    from app.apis.notifications.worker import channels, consumer
    from app.apis.notifications.worker.sweeper import sweep_outbox_once
    from app.core.configs.config import settings

    monkeypatch.setattr(
        TokenService,
        "create_activation_token",
        AsyncMock(return_value=ActivationKey("b" * 32)),
    )
    monkeypatch.setattr(consumer, "_build_realtime_service", lambda: None)
    monkeypatch.setattr(settings.SMTP, "host", "smtp.gmail.com")
    monkeypatch.setattr(settings.SMTP, "port", 587)
    monkeypatch.setattr(settings.SMTP, "use_tls", True)
    monkeypatch.setattr(settings.SMTP, "use_ssl", False)
    monkeypatch.setattr(settings.SMTP, "username", "sender@example.com")
    monkeypatch.setattr(settings.SMTP, "password", "test-app-password")
    smtp = MagicMock()
    factory = MagicMock(return_value=smtp)
    monkeypatch.setattr(channels.smtplib, "SMTP", factory)
    response = await client.post(
        "/users/register", json={"username": "queued", "email": "queued@example.com"}
    )
    assert response.status_code == 200
    broker = SimpleNamespace(publish=AsyncMock())
    assert (
        await sweep_outbox_once(sessionmaker=mock_db.sessionmaker, broker=broker) == 1
    )
    envelope = broker.publish.call_args.args[0]
    worker = consumer.NotificationWorker(
        cfg=consumer.WorkerConfig(
            amqp_url="unused",
            exchange_name="events",
            queue_name="test",
            bindings=["users.activation.requested"],
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
    server = smtp.__enter__.return_value
    server.starttls.assert_called_once()
    server.login.assert_called_once_with("sender@example.com", "test-app-password")
    email = server.send_message.call_args.args[0]
    assert email["To"] == "queued@example.com"
    assert (
        "/activate/" + "b" * 32
        in email.get_body(preferencelist=("plain",)).get_content()
    )
    async with mock_db.begin() as session:
        delivery = await session.scalar(select(NotificationDelivery))
        assert delivery.status.value == "sent"


@pytest.mark.asyncio
async def test_activation_can_retry_after_transaction_failure(
    client, mock_db, monkeypatch
):
    from unittest.mock import AsyncMock

    from app.apis.users.schema import UserActivationRequest
    from app.apis.users.user_service import UserService
    from app.core.redis.service import RedisService

    payload = UserBase(username="retryactivation", email="retryactivation@example.com")
    monkeypatch.setattr(
        RedisService, "get", AsyncMock(return_value=payload.model_dump_json())
    )
    delete = AsyncMock()
    monkeypatch.setattr(RedisService, "delete", delete)
    async with mock_db.begin() as session:
        session.add(
            User(
                username=payload.username,
                email=payload.email,
                hashed_password="unused",
                is_active=False,
            )
        )
    key = ActivationKey("c" * 32)
    with pytest.raises(RuntimeError):
        async with mock_db.begin() as session:
            await UserService(session).create_user(
                key,
                UserActivationRequest(password="Secret1", confirm_password="Secret1"),
            )
            raise RuntimeError("Simulate rollback after activation")
    response = await client.post(
        f"/users/activate/{key}",
        json={"password": "Secret1", "confirm_password": "Secret1"},
    )
    assert response.status_code == 201
    replay = await client.post(
        f"/users/activate/{key}",
        json={"password": "Different1", "confirm_password": "Different1"},
    )
    assert replay.status_code == 400
    delete.assert_not_awaited()
