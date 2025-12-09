# app/apis/homeuser/schema.py
from pydantic import BaseModel

from app.apis.homeuser.models import UserType


class HomeUserBase(BaseModel):
    user_id: int
    home_id: int
    user_type: UserType


class HomeUserCreate(HomeUserBase):
    pass


class HomeUserRead(HomeUserBase):
    pass


class HomeUserAddRequest(BaseModel):
    user_id: int
    user_type: UserType
