from datetime import datetime
from uuid import UUID

from pydantic import EmailStr, Field

from app.apis.homeuser.models import UserType
from app.schemas_base.base import BaseApiSchema, PaginatedOutput


class HomeBase(BaseApiSchema):
    name: str = Field(..., min_length=2, max_length=100)
    user_type: UserType | None = UserType.OWNER


class HomeCreate(HomeBase):
    pass


class HomeRead(HomeBase):
    id: UUID
    created_at: datetime
    updated_at: datetime


class GetHomesResponse(BaseApiSchema):
    user_id: UUID
    username: str
    email: EmailStr
    role: UserType


class GetHomeWithMembersResponse(BaseApiSchema):
    home_id: UUID
    name: str
    members: list[GetHomesResponse]
    created_at: datetime
    updated_at: datetime


class PaginatedAdminHomesResponse(PaginatedOutput[GetHomesResponse]):
    results: list[GetHomeWithMembersResponse]
