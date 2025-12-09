from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String

from app.core.database.base import SQLBase, TimeStampMixin


class Home(SQLBase, TimeStampMixin):
    __tablename__ = "homes"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
