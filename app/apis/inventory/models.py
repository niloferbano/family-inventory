from datetime import datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import Date
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import (HomeId, InventoryId, SQLBase,
                                    TimeStampMixin, UserId)


class InventoryCategory(Enum):
    KITCHEN = "kitchen"
    BATHROOM = "bathroom"
    CLEANING = "cleaning"
    OTHER = "other"


class InventoryItem(SQLBase, TimeStampMixin):
    __tablename__ = "inventory_items"

    id: Mapped[InventoryId] = mapped_column(primary_key=True, default=uuid4)
    home_id: Mapped[HomeId] = mapped_column(
        ForeignKey("homes.id", ondelete="CASCADE"), nullable=False
    )
    created_by: Mapped[UserId] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    category: Mapped[InventoryCategory] = mapped_column(
        SAEnum(
            InventoryCategory,
            name="inventory_category_enum",
            values_callable=lambda enum: [e.value for e in enum],
            create_constraint=True,
            native_enum=True,
        ),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit: Mapped[str] = mapped_column(String(30), default="pcs")

    expiry_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "home_id",
            "name",
            name="uq_inventory_home_name",
        ),
        Index(
            "ix_inventory_home_created_at",
            "home_id",
            "created_at",
        ),
        Index(
            "ix_inventory_home_category",
            "home_id",
            "category",
        ),
        Index(
            "ix_inventory_home_expiry",
            "home_id",
            "expiry_date",
        ),
    )
