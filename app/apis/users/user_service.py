import secrets
from urllib.parse import quote
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.apis.notifications.models import NotificationOutbox
from app.apis.notifications.repository import NotificationOutboxRepository
from app.apis.users.exceptions import UserAlreadyExists, UserNameAlreadyExists
from app.apis.users.models import User as UserModel
from app.apis.users.repository import UserRepository
from app.apis.users.schema import (GetUserResponse, PaginatedUsersResponse,
                                   UserActivationRequest, UserBase,
                                   UserRegisterResponse)
from app.core.configs.config import settings
from app.core.database.pagination import Page, apply_pagination
from app.iam.password_service import PasswordService
from app.iam.token_service import TokenService
from app.iam.types import ActivationKey


class UserService:
    def __init__(self, session) -> None:
        self.session = session
        self.user_repo = UserRepository(session=session)

    async def create_user(
        self,
        activation_key: ActivationKey,
        user_input: UserActivationRequest,
    ) -> UserModel:

        raw_user_data = await TokenService.verify_activation_token(activation_key)

        if not raw_user_data:
            raise ValueError("Invalid or expired activation token")

        user_base = UserBase.model_validate_json(raw_user_data)

        user = await self.session.scalar(
            select(UserModel)
            .where(UserModel.email == user_base.email)
            .with_for_update()
        )
        if user is None or user.is_active or user.username != user_base.username:
            raise ValueError("Invalid or expired activation token")
        user.hashed_password = PasswordService.hash(
            user_input.password.get_secret_value()
        )
        user.is_active = True
        await self.session.flush()
        return user

    async def register_user(self, user_data: UserBase) -> UserRegisterResponse:

        if await self.user_repo.get_by_email(email=user_data.email):
            raise UserAlreadyExists()
        user = UserModel(
            username=user_data.username,
            email=str(user_data.email),
            hashed_password=PasswordService.hash(secrets.token_urlsafe(32)),
            is_active=False,
        )
        try:
            await self.user_repo.create(user)
        except IntegrityError:
            raise UserNameAlreadyExists()
        token = await TokenService.create_activation_token(user_data=user_data)
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
        return UserRegisterResponse()

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
