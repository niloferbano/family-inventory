from datetime import datetime
from typing import Generic

from passlib.context import CryptContext
from pydantic import (EmailStr, Field, SecretStr, ValidationInfo,
                      field_validator)

from app.iam.types import ActivationKey, HashedString
from app.schemas_base.base import BaseApiSchema, PaginatedOutput
from app.schemas_base.protocols import OrmModelProtocolT

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def validate_password(value: SecretStr) -> SecretStr:
    pwd = value.get_secret_value()
    if len(pwd) < 6:
        raise ValueError("Password must be at least 6 characters")
    if not any(c.isdigit() for c in pwd):
        raise ValueError("Password must contain a number")
    return value


class UserBase(BaseApiSchema):
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr


class UserActivationRequest(BaseApiSchema):
    password: SecretStr
    confirm_password: SecretStr

    @field_validator("password")
    def password_criteria(cls, value: SecretStr):
        return validate_password(value)

    @field_validator("confirm_password")
    def password_match(cls, value: SecretStr, info: ValidationInfo) -> SecretStr:
        if (
            "password" in info.data
            and value.get_secret_value() != info.data["password"].get_secret_value()
        ):
            raise ValueError("Passwords do not match")
        return value

    # def hash_password(self) -> str:
    #     plain_bytes = self.password.get_secret_value().encode('utf-8')[:72]
    #     return pwd_context.hash(plain_bytes.decode('utf-8', errors='ignore'))


class UserRead(UserBase):
    id: int
    username: str
    email: EmailStr
    is_active: bool
    is_admin: bool
    home_id: int | None
    created_at: datetime
    updated_at: datetime


class GetUserResponse(UserBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class PaginatedUsersResponse(
    PaginatedOutput[GetUserResponse],
    Generic[OrmModelProtocolT],
):
    results: list[GetUserResponse] = Field(
        ...,
        description="List of users.",
    )


class UserLogin(BaseApiSchema):
    email: EmailStr
    password: HashedString


class TokenResponse(BaseApiSchema):
    access_token: str
    token_type: str = "bearer"


class UserRegisterResponse(BaseApiSchema):
    message: str = "User created. Activate your account."
    activation_key: ActivationKey
