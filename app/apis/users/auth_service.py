from sqlalchemy.ext.asyncio import AsyncSession

from app.apis.users.exceptions import InvalidCredentials
from app.apis.users.repository import UserRepository
from app.iam.password_service import PasswordService
from app.iam.schema import JWTPayload, TokenResponse
from app.iam.token_service import TokenService


class AuthService:
    def __init__(self, session: AsyncSession):
        self.user_repo = UserRepository(session)

    async def login(self, email: str, password: str):
        user = await self.user_repo.get_by_email(email)
        if not user:
            raise InvalidCredentials()

        if not PasswordService.verify(
            password=password, hashed_password=user.hashed_password
        ):
            raise InvalidCredentials()
        payload = JWTPayload(
            user_id=str(user.id), is_admin=user.is_admin, email=user.email
        )

        access_token = TokenService.create_access_token(payload)
        return TokenResponse(access_token=access_token)
