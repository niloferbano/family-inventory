import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.apis.notifications.models import NotificationOutbox
from app.apis.notifications.repository import NotificationOutboxRepository
from app.apis.users.exceptions import InvalidCredentials, InvalidResetToken
from app.apis.users.models import User
from app.apis.users.repository import UserRepository
from app.core.configs.config import settings
from app.core.logging import get_logger
from app.core.redis.client import redis_client
from app.iam.password_service import PasswordService
from app.iam.schema import JWTBasePayload, TokenResponse
from app.iam.token_service import TokenService

logger = get_logger(__name__)
RESET_TOPIC = "users.password_reset.requested"


class AuthService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)

    async def login(self, email: str, password: str):
        user = await self.user_repo.get_by_email(email)
        if not user or not user.is_active:
            raise InvalidCredentials()

        if not PasswordService.verify(
            password=password, hashed_password=user.hashed_password
        ):
            raise InvalidCredentials()
        payload = JWTBasePayload(
            user_id=str(user.id), is_admin=user.is_admin, email=user.email
        )

        access_token = TokenService.create_access_token(payload)
        return TokenResponse(access_token=access_token)

    async def request_password_reset(self, email: str) -> None:
        # Serialize requests and confirmation on the user row. Replacing the hash
        # invalidates every previous reset link in the same transaction as enqueueing.
        allowed = await redis_client.set(
            f"password-reset:{email}",
            "1",
            nx=True,
            ex=settings.PASSWORD_RESET_COOLDOWN_SECONDS,
        )
        logger.info("password_reset_requested", throttled=not bool(allowed))
        if not allowed:
            return
        user = await self.user_repo.get_by_email(email=email, for_update=True)
        if user is None or not user.is_active:
            return
        token = secrets.token_urlsafe(32)
        user.password_reset_hash = hashlib.sha256(token.encode()).hexdigest()
        user.password_reset_expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=settings.PASSWORD_RESET_EXPIRE_MINUTES
        )
        event_id = uuid4()
        link = f"{str(settings.PUBLIC_BASE_URL).rstrip('/')}/reset-password/{token}"
        NotificationOutboxRepository(self.session).add(
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

    async def reset_password(self, token: str, password: str) -> None:
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
