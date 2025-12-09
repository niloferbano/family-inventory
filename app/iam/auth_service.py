"""Authentication service stubs for IAM."""

from app.iam.password_service import PasswordService
from app.iam.token_service import TokenService


class AuthService:
    """Handles authentication workflows."""

    def __init__(self, password_service: PasswordService, token_service: TokenService):
        self.password_service = password_service
        self.token_service = token_service

    async def authenticate(self, username: str, password: str):
        """Validate credentials and return a token."""
        raise NotImplementedError
