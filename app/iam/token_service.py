import secrets
import uuid
from datetime import datetime, timedelta, timezone

from jose import jwt

from app.apis.users.schema import UserBase
from app.core.configs.config import settings
from app.core.redis.service import RedisService
from app.iam.schema import JWTBasePayload, JWTPayload
from app.iam.types import ActivationKey


class TokenService:
    ACTIVATION_PREFIX = "activation"

    @staticmethod
    def create_access_token(data: JWTBasePayload) -> str:
        now = datetime.now(timezone.utc)

        payload = {
            "user_id": str(data.user_id),
            "email": data.email,
            "is_admin": data.is_admin,
            "iat": int(now.timestamp()),
            "exp": int(
                (
                    now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
                ).timestamp()
            ),
            "jti": str(uuid.uuid4()),
        }

        return jwt.encode(
            payload,
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )

    @staticmethod
    def decode_token(token: str) -> JWTPayload:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return JWTPayload.model_validate(payload)

    @staticmethod
    def generate_token() -> ActivationKey:
        return ActivationKey(secrets.token_urlsafe(32))

    @classmethod
    async def create_activation_token(cls, user_data: UserBase) -> ActivationKey:
        token = cls.generate_token()
        key = f"{cls.ACTIVATION_PREFIX}:{str(token)}"

        ttl = settings.ACTIVATION_TOKEN_EXPIRE_MINUTES * 60

        await RedisService.set(key, user_data.model_dump_json(), ttl=ttl)

        return token

    @classmethod
    async def verify_activation_token(cls, token: ActivationKey) -> str:
        key = f"{cls.ACTIVATION_PREFIX}:{str(token)}"

        user_data = await RedisService.get(key)
        if not user_data:
            raise ValueError("Invalid or expired activation token")

        await RedisService.delete(key)

        return user_data
