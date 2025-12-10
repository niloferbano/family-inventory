# app/apis/homeuser/schema.py
from pydantic import BaseModel, EmailStr

from app.apis.homeuser.models import UserType
from app.schemas_base.base import BaseApiSchema


class HomeUserBase(BaseApiSchema):
    user_id: int
    home_id: int
    user_type: UserType


class HomeUserCreate(HomeUserBase):
    pass


class HomeUserAddResponse(BaseApiSchema):
    username: str
    home_name: str
    user_type: UserType


class HomeUserAddRequest(BaseModel):
    user_email: EmailStr
    user_type: UserType
