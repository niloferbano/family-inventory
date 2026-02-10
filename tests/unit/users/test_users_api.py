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
async def test_register_user_returns_activation_key(client, monkeypatch):
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
    assert body["activation_key"] == "a" * 32


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
