from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column
from pydantic import EmailStr

from app.core.database.base import SQLBase, TimeStampMixin
from app.iam.types import HashedString


class User(SQLBase, TimeStampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    username: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    email: Mapped[EmailStr] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[HashedString] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(default=False)