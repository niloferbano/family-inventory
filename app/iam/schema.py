from datetime import datetime

from pydantic import EmailStr, Field

from app.schemas_base.base import BaseApiSchema


class TokenResponse(BaseApiSchema):
    access_token: str
    token_type: str = "bearer"


class JWTPayload(BaseApiSchema):

    user_id: str = Field(..., description="User ID")
    email: EmailStr = Field(..., description="User email address")
    is_admin: bool = Field(default=False, description="Platform-wide admin flag")
    exp: datetime = Field(..., description="Token expiration timestamp")
