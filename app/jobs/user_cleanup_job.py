"""Delete stale inactive accounts; run once or as a scheduled container."""

import asyncio
import sys
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa

from app.apis.users.models import User
from app.core.configs.config import settings
from app.core.database.session import get_db
from app.core.logging import get_logger

logger = get_logger(__name__)


async def cleanup_users(session, *, now=None):
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=settings.UNACTIVATED_USER_RETENTION_DAYS)
    result = await session.execute(
        sa.delete(User).where(
            User.is_active.is_(False),
            User.created_at < cutoff,
            sa.or_(
                User.activation_expires_at.is_(None), User.activation_expires_at <= now
            ),
        )
    )
    return result.rowcount


async def main():
    db = get_db()
    try:
        await db.connect()
        while True:
            try:
                async with db.begin() as session:
                    count = await cleanup_users(session)
                logger.info("unactivated_users_cleaned", count=count)
            except Exception:
                logger.exception("unactivated_user_cleanup_failed")
                if "--loop" not in sys.argv:
                    raise
            if "--loop" not in sys.argv:
                break
            await asyncio.sleep(settings.USER_CLEANUP_INTERVAL_SECONDS)
    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
