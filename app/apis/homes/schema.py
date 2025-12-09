from pydantic import BaseModel
from pydantic import Field
from datetime import datetime

from app.apis.homeuser.models import UserType



class HomeBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    user_type: UserType | None = UserType.HOME_OWNER

class HomeCreate(HomeBase):
    pass

class HomeRead(HomeBase):
    id: int
    created_at: datetime
    updated_at: datetime