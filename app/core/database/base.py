from datetime import datetime
from typing import NewType
from uuid import UUID as PythonUUID

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

HomeId = NewType("HomeId", PythonUUID)
UserId = NewType("UserId", PythonUUID)


class SQLBase(DeclarativeBase):
    pass


class TimeStampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=func.now(),  # ensure value on insert when server_default not applied
        onupdate=func.now(),  # auto-updates on UPDATE statements
        nullable=True,
        index=True,
    )
