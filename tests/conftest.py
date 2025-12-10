import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.apis.users.models import User
from app.core.configs.config import settings
from app.core.database.base import SQLBase
from app.core.database.session import DBManager, get_db, get_session
from app.iam.schema import JWTBasePayload
from app.iam.token_service import TokenService
from app.main import app


@pytest.fixture
def worker_schema():
    return f"test_schema_{uuid.uuid4().hex}"


@pytest_asyncio.fixture(scope="function")
async def mock_db(worker_schema):
    mock_db = DBManager(
        model_base=SQLBase,
        db_url=settings.TEST_DATABASE_URL,
        connect_args={"server_settings": {"search_path": worker_schema}},
        pool_size=5,
    )

    async with mock_db.engine.begin() as conn:
        await conn.execute(text(f'DROP SCHEMA IF EXISTS "{worker_schema}" CASCADE'))
        await conn.execute(text(f'CREATE SCHEMA "{worker_schema}"'))
        await conn.execute(
            text(f'SET search_path TO "{worker_schema}", public, pg_catalog')
        )
        await conn.run_sync(SQLBase.metadata.create_all)

    app.dependency_overrides[get_db] = lambda: mock_db

    async def _get_test_session():
        async with mock_db.sessionmaker() as session:
            yield session

    app.dependency_overrides[get_session] = _get_test_session

    try:
        yield mock_db
    finally:
        app.dependency_overrides.clear()
        await mock_db.disconnect()


@pytest_asyncio.fixture
async def client(mock_db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def auth_headers(mock_db):
    async with mock_db.sessionmaker() as session:
        user = User(
            username="authuser",
            email="auth@example.com",
            hashed_password="hashed",
            is_active=True,
            is_admin=False,
        )

        session.add(user)
        await session.commit()
        await session.refresh(user)

        payload = JWTBasePayload(
            user_id=str(user.id),
            email=user.email,
            is_admin=user.is_admin,
        )

        token = TokenService.create_access_token(payload)
        return {"Authorization": f"Bearer {token}"}
