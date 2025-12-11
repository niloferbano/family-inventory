# app/apis/homeuser/schema.py
import uuid

from pydantic import EmailStr

from app.apis.homeuser.models import UserType
from app.schemas_base.base import BaseApiSchema


class HomeUserBase(BaseApiSchema):
    user_id: uuid.UUID
    home_id: uuid.UUID
    user_type: UserType


class HomeUserCreate(HomeUserBase):
    pass


class HomeUserAddResponse(BaseApiSchema):
    username: str
    home_name: str
    user_type: UserType


class HomeUserAddRequest(BaseApiSchema):
    user_email: EmailStr
    user_type: UserType


class ChangeHomeUserRoleRequest(BaseApiSchema):
    user_type: UserType
