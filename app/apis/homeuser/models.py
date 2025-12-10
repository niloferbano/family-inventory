# app/apis/homeuser/models.py
from enum import Enum

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Index, PrimaryKeyConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import SQLBase, TimeStampMixin


class UserType(Enum):
    HOME_OWNER = "owner"
    HOME_RESIDENCE = "residence"
    GUEST = "guest"


class HomeUser(SQLBase, TimeStampMixin):
    __tablename__ = "home_users"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    home_id: Mapped[int] = mapped_column(
        ForeignKey("homes.id", ondelete="CASCADE"),
        nullable=False,
    )

    user_type: Mapped[UserType] = mapped_column(
        SAEnum(UserType, name="user_type_enum"),
        nullable=False,
    )

    __table_args__ = (
        PrimaryKeyConstraint("user_id", "home_id", name="pk_user_home"),
        Index("ix_home_users_user_id", "user_id"),
        Index("ix_home_users_home_id", "home_id"),
    )
