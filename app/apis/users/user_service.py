from sqlalchemy.exc import IntegrityError

from app.apis.users.exceptions import UserAlreadyExists, UserNameAlreadyExists
from app.apis.users.models import User as UserModel
from app.apis.users.repository import UserRepository
from app.apis.users.schema import (GetUserResponse, PaginatedUsersResponse,
                                   UserActivationRequest, UserBase,
                                   UserRegisterResponse)
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

        if await self.user_repo.get_by_email(user_base.email):
            raise UserAlreadyExists()

        user_model = UserModel(
            username=user_base.username,
            email=user_base.email,
            hashed_password=PasswordService.hash(
                user_input.password.get_secret_value()
            ),
            is_active=True,
        )
        try:
            return await self.user_repo.create(user_model)
        except IntegrityError:
            raise UserNameAlreadyExists()

    async def register_user(self, user_data: UserBase) -> UserRegisterResponse:

        if await self.user_repo.get_by_email(email=user_data.email):
            raise UserAlreadyExists()
        token = await TokenService.create_activation_token(user_data=user_data)

        return UserRegisterResponse(
            message="User created. Activate your account.", activation_key=token
        )

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
