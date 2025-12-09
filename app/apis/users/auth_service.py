
from sqlalchemy.ext.asyncio import AsyncSession

from app.apis.users.exceptions import InvalidCredentials
from app.apis.users.repository import UserRepository
from app.iam.password_service import PasswordService
from app.iam.schema import TokenResponse
from app.iam.token_service import TokenService

class AuthService:
    def __init__(self, session: AsyncSession):
        self.user_repo = UserRepository(session)

    async def login(self, email: str, password: str):
        user = await self.user_repo.get_by_email(email)
        if not user:
            raise InvalidCredentials()

        if not PasswordService.verify(password=password, hashed_password=user.hashed_password):
            raise InvalidCredentials()

        access_token = TokenService.create_access_token({"sub": str(user.id)})
        return TokenResponse(access_token=access_token)
