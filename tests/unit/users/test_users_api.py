import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.apis.notifications.models import NotificationOutbox
from app.apis.users.models import User
from app.apis.users.repository import UserRepository
from app.apis.users.schema import UserBase, UserRegisterResponse
from app.iam.password_service import PasswordService
from app.iam.token_service import TokenService
from app.iam.types import ActivationKey


@pytest.mark.asyncio
async def test_concurrent_registration_same_details(client, mock_db, monkeypatch):
    both_ready = asyncio.Event()
    attempts = 0
    conflicts = 0
    create = UserRepository.create

    async def synchronized_create(repo, user):
        nonlocal attempts, conflicts
        attempts += 1
        if attempts == 2:
            both_ready.set()
        # Both requests must pass the existence checks before either inserts.
        await asyncio.wait_for(both_ready.wait(), timeout=5)
        try:
            return await create(repo, user)
        except IntegrityError:
            conflicts += 1
            raise

    async def fake_create_activation_token(cls, user_data):
        return ActivationKey("c" * 32)

    monkeypatch.setattr(UserRepository, "create", synchronized_create)
    monkeypatch.setattr(
        TokenService,
        "create_activation_token",
        classmethod(fake_create_activation_token),
    )
    payload = {"username": "concurrent", "email": "concurrent@example.com"}
    responses = await asyncio.wait_for(
        asyncio.gather(
            client.post("/users/register", json=payload),
            client.post("/users/register", json=payload),
        ),
        timeout=15,
    )

    assert attempts == 2
    assert conflicts == 1
    assert sorted(response.status_code for response in responses) == [200, 409]
    for response in responses:
        if response.status_code == 200:
            assert response.json() == UserRegisterResponse().model_dump()
        else:
            # Resolving this conflict requires a working query after rollback
            # to the savepoint; an aborted outer transaction would fail here.
            assert response.json() == {
                "detail": "Username is unavailable. Please choose another username."
            }

    async with mock_db.begin() as session:
        users = (await session.scalars(select(User))).all()
        assert len(users) == 1
        assert users[0].username == payload["username"]
        assert users[0].email == payload["email"]
        assert not users[0].is_active
        outbox = (await session.scalars(select(NotificationOutbox))).all()
        assert len(outbox) == 1
        assert outbox[0].topic == "users.activation.requested"
        assert outbox[0].payload["user_id"] == str(users[0].id)


@pytest.mark.asyncio
@pytest.mark.parametrize("duplicate", ["email", "username", "both"])
async def test_register_insert_conflict_after_checks(
    client, db_session, monkeypatch, duplicate
):
    existing = User(
        username="existing",
        email="dup@example.com",
        hashed_password="unchanged",
        is_active=False,
    )
    db_session.add(existing)
    await db_session.commit()
    username_checks = 0
    email_checks = 0
    conflicts = 0
    get_by_username = UserRepository.get_by_username
    get_by_email = UserRepository.get_by_email
    create = UserRepository.create

    async def initially_missing_username(repo, username):
        nonlocal username_checks
        username_checks += 1
        if username_checks == 1:
            return None
        # Execute a real query in the request's transaction after the failed
        # insert. This fails if the savepoint did not restore the session.
        return await get_by_username(repo, username)

    async def initially_missing_email(repo, email, **kwargs):
        nonlocal email_checks
        email_checks += 1
        if email_checks == 1:
            return None
        return await get_by_email(repo, email, **kwargs)

    async def real_insert(repo, user):
        nonlocal conflicts
        try:
            return await create(repo, user)
        except IntegrityError:
            conflicts += 1
            raise

    monkeypatch.setattr(UserRepository, "get_by_username", initially_missing_username)
    monkeypatch.setattr(UserRepository, "get_by_email", initially_missing_email)
    monkeypatch.setattr(UserRepository, "create", real_insert)
    response = await client.post(
        "/users/register",
        json={
            "username": "newuser" if duplicate == "email" else "existing",
            "email": (
                "new@example.com" if duplicate == "username" else "dup@example.com"
            ),
        },
    )

    assert conflicts == 1
    assert username_checks == 2
    assert email_checks == 1
    if duplicate == "email":
        assert response.status_code == 200
        assert response.json() == UserRegisterResponse().model_dump()
    else:
        assert response.status_code == 409
        assert response.json() == {
            "detail": "Username is unavailable. Please choose another username."
        }
    assert (await db_session.scalars(select(User))).all() == [existing]
    assert (await db_session.scalars(select(NotificationOutbox))).all() == []
    await db_session.refresh(existing)
    assert existing.hashed_password == "unchanged"
    assert not existing.is_active


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
    assert body == UserRegisterResponse().model_dump()
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
@pytest.mark.parametrize("active", [True, False])
@pytest.mark.parametrize("duplicate", ["email", "username", "both"])
async def test_register_duplicate_preserves_email_privacy(
    client, db_session, active, duplicate
):
    user = User(
        username="existing",
        email="dup@example.com",
        hashed_password="hashed",
        is_active=active,
        is_admin=False,
    )
    db_session.add(user)
    await db_session.commit()

    res = await client.post(
        "/users/register",
        json={
            "username": "existing" if duplicate in ("username", "both") else "newuser",
            "email": (
                "new@example.com" if duplicate == "username" else "dup@example.com"
            ),
        },
    )

    if duplicate == "email":
        assert res.status_code == 200
        assert res.json() == UserRegisterResponse().model_dump()
    else:
        assert res.status_code == 409
        assert res.json() == {
            "detail": "Username is unavailable. Please choose another username."
        }
    from app.apis.notifications.models import NotificationOutbox

    assert (await db_session.scalars(select(NotificationOutbox))).all() == []
    await db_session.refresh(user)
    assert user.is_active == active
    assert user.hashed_password == "hashed"


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
@pytest.mark.parametrize("resend", [False, True])
async def test_activation_outbox_through_consumer_and_email_sender(
    client, mock_db, monkeypatch, resend
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
    if resend:
        async with mock_db.begin() as session:
            session.add(
                User(
                    username="queued",
                    email="queued@example.com",
                    hashed_password="unused",
                    is_active=False,
                )
            )
        monkeypatch.setattr(
            "app.apis.users.user_service.redis_client.set", AsyncMock(return_value=True)
        )
        response = await client.post(
            "/users/resend-activation", json={"email": "queued@example.com"}
        )
    else:
        response = await client.post(
            "/users/register",
            json={"username": "queued", "email": "queued@example.com"},
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
