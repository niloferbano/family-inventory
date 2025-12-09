import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import jwt

from app.apis.users.schema import UserBase
from app.core.configs.config import settings
from app.core.redis.service import RedisService
from app.iam.types import ActivationKey


class TokenService:
    ACTIVATION_PREFIX = "activation"

    @staticmethod
    def create_access_token(data: dict[str, Any]) -> str:
        """
        Create a signed JWT access token.
        Includes:
        - exp: expiration time
        - iat: issued time
        - jti: unique token identifier
        """

        now = datetime.now(timezone.utc)

        payload = {
            **data,
            "iat": now,
            "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
            "jti": str(uuid.uuid4()),  # unique token ID
        }

        return jwt.encode(
            payload,
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )

    @staticmethod
    def decode_token(token: str) -> dict:
        return jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )

    @staticmethod
    def generate_token() -> ActivationKey:
        """Create a secure random activation token."""
        return ActivationKey(secrets.token_urlsafe(32))

    @classmethod
    async def create_activation_token(cls, user_data: UserBase) -> ActivationKey:
        token = cls.generate_token()
        key = cls.ACTIVATION_PREFIX + token

        ttl = settings.ACTIVATION_TOKEN_EXPIRE_MINUTES * 60

        # Store token → user_id mapping
        await RedisService.set(key, user_data.model_dump_json(), ttl=ttl)

        return token

    @classmethod
    async def verify_activation_token(cls, token: ActivationKey) -> str:
        key = cls.ACTIVATION_PREFIX + str(token)

        user_data = await RedisService.get(key)
        if not user_data:
            raise ValueError("Invalid or expired activation token")

        await RedisService.delete(key)

        return user_data
