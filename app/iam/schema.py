from pydantic import EmailStr

from app.schemas_base.base import BaseApiSchema


class TokenResponse(BaseApiSchema):
    access_token: str
    token_type: str = "bearer"


class JWTBasePayload(BaseApiSchema):
    user_id: str
    email: EmailStr
    is_admin: bool = False


class JWTPayload(JWTBasePayload):
    iat: int
    exp: int
    jti: str
