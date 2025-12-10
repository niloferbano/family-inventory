from datetime import datetime

from pydantic import EmailStr, Field

from app.apis.homeuser.models import UserType
from app.schemas_base.base import BaseApiSchema


class HomeBase(BaseApiSchema):
    name: str = Field(..., min_length=2, max_length=100)
    user_type: UserType | None = UserType.OWNER


class HomeCreate(HomeBase):
    pass


class HomeRead(HomeBase):
    id: int
    created_at: datetime
    updated_at: datetime


class GetHomesResponse(BaseApiSchema):
    id: int
    username: str
    email: EmailStr
    role: UserType


class GetHomeWithMembersResponse(BaseApiSchema):
    id: int
    name: str
    members: list[GetHomesResponse]
