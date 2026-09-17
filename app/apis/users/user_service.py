import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from uuid import uuid4

from pydantic import EmailStr
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.apis.notifications.models import NotificationOutbox
from app.apis.notifications.repository import NotificationOutboxRepository
from app.apis.users.exceptions import (InvalidActivationToken,
                                       UserAlreadyActive, UserAlreadyExists,
                                       UserNameAlreadyExists)
from app.apis.users.models import User as UserModel
from app.apis.users.repository import UserRepository
from app.apis.users.schema import (GetUserResponse, PaginatedUsersResponse,
                                   ResendActivationResponse,
                                   UserActivationRequest, UserBase,
                                   UserRegisterResponse)
from app.core.configs.config import settings
from app.core.database.pagination import Page, apply_pagination
from app.core.logging import get_logger
from app.core.redis.client import redis_client
from app.iam.password_service import PasswordService
from app.iam.token_service import TokenService
from app.iam.types import ActivationKey

logger = get_logger(__name__)


class UserService:
    def __init__(self, session) -> None:
        self.session = session
        self.user_repo = UserRepository(session=session)

    async def create_user(
        self,
        activation_key: ActivationKey,
        user_input: UserActivationRequest,
    ) -> UserModel:

        try:
            raw_user_data = await TokenService.verify_activation_token(activation_key)
        except ValueError as exc:
            raise InvalidActivationToken() from exc

        if not raw_user_data:
            raise InvalidActivationToken()

        user_base = UserBase.model_validate_json(raw_user_data)

        user = await self.session.scalar(
            select(UserModel)
            .where(UserModel.email == user_base.email)
            .with_for_update()
        )
        if user is None or user.is_active or user.username != user_base.username:
            raise InvalidActivationToken()
        if user.activation_token_hash is not None and (
            user.activation_token_hash
            != hashlib.sha256(str(activation_key).encode()).hexdigest()
            or user.activation_expires_at is None
            or user.activation_expires_at <= datetime.now(timezone.utc)
        ):
            raise InvalidActivationToken()
        user.hashed_password = PasswordService.hash(
            user_input.password.get_secret_value()
        )
        user.is_active = True
        await self.session.flush()
        return user

    async def register_user(self, user_data: UserBase) -> UserRegisterResponse:
        # Check independently of email so this error cannot reveal whether
        # the submitted email belongs to an existing account.
        if await self.user_repo.get_by_username(user_data.username):
            raise UserNameAlreadyExists()
        user_db = await self.user_repo.get_by_email(email=user_data.email)
        if user_db:
            if not user_db.is_active:
                await self._queue_activation(user_db, user_data)
                return UserRegisterResponse()
            else:
                raise UserAlreadyExists()
        user = UserModel(
            username=user_data.username,
            email=str(user_data.email),
            hashed_password=PasswordService.hash(secrets.token_urlsafe(32)),
            is_active=False,
        )
        try:
            # Preserve the transaction so a concurrent collision can be checked.
            async with self.session.begin_nested():
                await self.user_repo.create(user)
        except IntegrityError as exc:
            if getattr(exc.orig, "sqlstate", None) != "23505":
                raise
            if await self.user_repo.get_by_username(user_data.username):
                raise UserNameAlreadyExists() from exc
            return UserRegisterResponse()
        await self._queue_activation(user, user_data)
        return UserRegisterResponse()

    async def validate_activation_link(self, key: str) -> None:
        input_hash = hashlib.sha256(str(key).encode()).hexdigest()
        try:
            raw_user_data = await TokenService.verify_activation_token(token=key)
        except ValueError:
            raw_user_data = None
        if not raw_user_data:
            user = await self.user_repo.get_by_activation_token_hash(input_hash)
            if user and user.is_active:
                raise UserAlreadyActive()
            raise InvalidActivationToken()
        user_base = UserBase.model_validate_json(raw_user_data)
        user = await self.user_repo.get_by_email(str(user_base.email))
        if user is None or user.username != user_base.username:
            raise InvalidActivationToken()
        if user.activation_token_hash is not None and (
            user.activation_token_hash != input_hash
            or user.activation_expires_at is None
            or user.activation_expires_at <= datetime.now(timezone.utc)
        ):
            raise InvalidActivationToken()
        if user.is_active:
            raise UserAlreadyActive()

    async def resend_activation(self, email: EmailStr) -> ResendActivationResponse:
        # Same response and throttle behavior for unknown, active and inactive users.
        key = hashlib.sha256(email.strip().lower().encode()).hexdigest()
        allowed = await redis_client.set(
            f"activation-resend:{key}",
            "1",
            nx=True,
            ex=settings.ACTIVATION_RESEND_COOLDOWN_SECONDS,
        )
        logger.info("activation_resend_requested", throttled=not bool(allowed))
        if not allowed:
            return ResendActivationResponse()
        user = await self.user_repo.get_by_email(email, for_update=True)
        if user is None or user.is_active:
            return ResendActivationResponse()
        await self._queue_activation(
            user, UserBase(username=user.username, email=user.email)
        )
        return ResendActivationResponse()

    async def _queue_activation(self, user: UserModel, user_data: UserBase) -> None:
        token = await TokenService.create_activation_token(user_data=user_data)
        user.activation_token_hash = hashlib.sha256(str(token).encode()).hexdigest()
        user.activation_expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=settings.ACTIVATION_TOKEN_EXPIRE_MINUTES
        )
        logger.info("activation_email_requested", user_id=str(user.id))
        event_id = uuid4()
        link = f"{str(settings.PUBLIC_BASE_URL).rstrip('/')}/activate/{quote(str(token), safe='')}"
        NotificationOutboxRepository(self.session).add(
            NotificationOutbox(
                event_id=event_id,
                topic="users.activation.requested",
                payload={
                    "event_id": str(event_id),
                    "user_id": str(user.id),
                    "subject": "Activate your Family Inventory account",
                    "message": f"Set your password to activate your account:\n\n{link}\n\n"
                    f"This link expires in {settings.ACTIVATION_TOKEN_EXPIRE_MINUTES} minutes. "
                    "If you did not request this account, ignore this email.",
                },
                headers={"source": "users", "event_id": str(event_id)},
            )
        )
        await self.session.flush()

    async def get_all_users(
        self,
        pagination: Page,
        request_url: str,
    ) -> PaginatedUsersResponse:

        query = self.user_repo.get_all_query()

        return await apply_pagination(  # type: ignore[type-var]
            query=query,
            session=self.session,
            sort_by=UserModel.id,
            pagination=pagination,
            base_url=request_url,
            row_model=GetUserResponse,
            paginated_output_model=PaginatedUsersResponse,
        )
