import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select

from app.apis.notifications.models import NotificationOutbox
from app.apis.notifications.repository.outbox_repository import \
    NotificationOutboxRepository
from app.apis.users.models import User
from app.core.configs.config import settings
from app.core.logging import get_logger
from app.iam.password_service import PasswordService

logger = get_logger(__name__)
RESET_TOPIC = "users.password_reset.requested"


class InvalidResetToken(Exception):
    pass


class PasswordResetService:
    def __init__(self, session):
        self.session = session
        self.notification_outbox_repo = NotificationOutboxRepository(
            session=self.session
        )

    async def request(self, email: str) -> None:
        # Serialize requests and confirmation on the user row. Replacing the hash
        # invalidates every previous reset link in the same transaction as enqueueing.
        user = await self.session.scalar(
            select(User).where(User.email == email).with_for_update()
        )
        logger.info("password_reset_requested")
        if user is None or not user.is_active:
            return
        token = secrets.token_urlsafe(32)
        user.password_reset_hash = hashlib.sha256(token.encode()).hexdigest()
        user.password_reset_expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=settings.PASSWORD_RESET_EXPIRE_MINUTES
        )
        event_id = uuid4()
        link = f"{str(settings.PUBLIC_BASE_URL).rstrip('/')}/reset-password/{token}"
        self.session.add(
            NotificationOutbox(
                event_id=event_id,
                topic=RESET_TOPIC,
                payload={
                    "event_id": str(event_id),
                    "user_id": str(user.id),
                    "subject": "Reset your Family Inventory password",
                    "message": f"Reset your password using this link:\n\n{link}\n\n"
                    f"This link expires in {settings.PASSWORD_RESET_EXPIRE_MINUTES} minutes. "
                    "If you did not request a password reset, ignore this email.",
                },
                headers={"source": "users", "event_id": str(event_id)},
            )
        )
        await self.session.flush()

    async def reset(self, token: str, password: str) -> None:
        digest = hashlib.sha256(token.encode()).hexdigest()
        user = await self.session.scalar(
            select(User).where(User.password_reset_hash == digest).with_for_update()
        )
        if (
            user is None
            or not user.is_active
            or user.password_reset_expires_at is None
            or user.password_reset_expires_at <= datetime.now(timezone.utc)
        ):
            logger.info("password_reset_rejected")
            raise InvalidResetToken()
        user.hashed_password = PasswordService.hash(password)
        user.password_reset_hash = None
        user.password_reset_expires_at = None
        await self.session.flush()
