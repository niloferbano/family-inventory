import datetime
from datetime import date
from uuid import UUID, uuid4

from sqlalchemy import Date, DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import (ForeignKey, Index, Integer, String, Text,
                        UniqueConstraint)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.apis.inventory.types import InventoryAlertType, InventoryCategory
from app.core.database.base import (HomeId, InventoryId, SQLBase,
                                    TimeStampMixin, UserId)


class InventoryItem(SQLBase, TimeStampMixin):
    __tablename__ = "inventory_items"

    id: Mapped[InventoryId] = mapped_column(primary_key=True, default=uuid4)
    home_id: Mapped[HomeId] = mapped_column(
        ForeignKey("homes.id", ondelete="CASCADE"), nullable=False
    )
    created_by: Mapped[UserId | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
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

    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
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


class InventoryExpiryAlert(SQLBase, TimeStampMixin):
    __tablename__ = "inventory_expiry_alerts"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )

    inventory_item_id: Mapped[InventoryId] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("inventory_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    alert_type: Mapped[InventoryAlertType] = mapped_column(
        SAEnum(
            InventoryAlertType,
            name="inventory_alert_type_enum",
            values_callable=lambda enum: [e.value for e in enum],
            create_constraint=True,
            native_enum=True,
        ),
        nullable=False,
    )
    alert_date: Mapped[date] = mapped_column(
        Date, nullable=False
    )  # day bucket (prevents daily duplicates)

    published_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    publish_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_publish_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "inventory_item_id",
            "alert_type",
            "alert_date",
            name="uq_item_alert_once_per_day",
        ),
    )
