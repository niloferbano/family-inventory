from uuid import uuid4

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import HomeId, SQLBase, TimeStampMixin


class Home(SQLBase, TimeStampMixin):
    __tablename__ = "homes"

    id: Mapped[HomeId] = mapped_column(primary_key=True, default=uuid4)

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
