from sqlalchemy.exc import IntegrityError

from app.apis.users.exceptions import UserAlreadyExists, UserNameAlreadyExists
from app.apis.users.models import User as UserModel
from app.apis.users.repository import UserRepository
from app.apis.users.schema import (UserActivationRequest, UserBase,
                                   UserRegisterResponse)
from app.iam.password_service import PasswordService
from app.iam.token_service import TokenService
from app.iam.types import ActivationKey


class UserService:
    def __init__(self, session) -> None:
        self.session = session

    async def create_user(
        self,
        activation_key: ActivationKey,
        user_input: UserActivationRequest,
    ) -> UserModel:

        raw_user_data = await TokenService.verify_activation_token(activation_key)

        if not raw_user_data:
            raise ValueError("Invalid or expired activation token")

        user_base = UserBase.model_validate_json(raw_user_data)

        repo = UserRepository(self.session)

        if await repo.get_by_email(user_base.email):
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
            return await repo.create(user_model)
        except IntegrityError:
            raise UserNameAlreadyExists()

    async def register_user(self, user_data: UserBase) -> UserRegisterResponse:
        user_repo = UserRepository(session=self.session)

        if await user_repo.get_by_email(email=user_data.email):
            raise UserAlreadyExists()
        token = await TokenService.create_activation_token(user_data=user_data)

        return UserRegisterResponse(
            message="User created. Activate your account.", activation_key=token
        )
