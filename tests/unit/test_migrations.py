import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.core.configs.config import settings


def _with_search_path(db_url: str, schema: str) -> str:
    # Avoid percent-encoding to keep Alembic's config parser happy.
    joiner = "&" if "?" in db_url else "?"
    return f"{db_url}{joiner}options=-csearch_path={schema},public"


def _can_connect(db_url: str) -> bool:
    engine = create_engine(db_url, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except (OperationalError, OSError, PermissionError):
        return False
    finally:
        engine.dispose()


def test_alembic_upgrade_head(monkeypatch):
    sync_db_url = settings.TEST_DATABASE_URL.replace("+asyncpg", "")
    if not _can_connect(sync_db_url):
        pytest.skip("Test database unavailable for Alembic migration test")

    schema = f"alembic_test_{uuid.uuid4().hex}"
    engine = create_engine(sync_db_url, pool_pre_ping=True)
    try:
        with engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))

        async_db_url = _with_search_path(settings.TEST_DATABASE_URL, schema)
        monkeypatch.setattr(settings, "DATABASE_URL", async_db_url)

        alembic_ini = Path(__file__).resolve().parents[2] / "alembic.ini"
        alembic_cfg = Config(str(alembic_ini))

        command.upgrade(alembic_cfg, "head")

        with engine.connect() as conn:
            result = conn.execute(
                text(f'SELECT version_num FROM "{schema}".alembic_version')
            ).fetchone()
            assert result is not None
    finally:
        with engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()
