import datetime
from datetime import date
from uuid import UUID, uuid4

from sqlalchemy import Date, DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.apis.household_categories.models import HouseholdCategory
from app.apis.inventory.types import InventoryAlertType
from app.apis.product.models import Product
from app.core.database.base import (
    HomeId,
    HouseholdCategoryId,
    InventoryId,
    ProductId,
    SQLBase,
    TimeStampMixin,
    UserId,
)


class InventoryItem(SQLBase, TimeStampMixin):
    __tablename__ = "inventory_items"

    id: Mapped[InventoryId] = mapped_column(primary_key=True, default=uuid4)
    home_id: Mapped[HomeId] = mapped_column(
        ForeignKey("homes.id", ondelete="CASCADE"), nullable=False
    )
    created_by: Mapped[UserId | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Nullable during the Product/StockBatch rollout (issue #40/#43):
    # existing rows have no product yet. ON DELETE RESTRICT because Product
    # is a shared/global catalog — deleting one must not silently orphan or
    # cascade-wipe another home's inventory history.
    product_id: Mapped[ProductId | None] = mapped_column(
        ForeignKey("inventory_products.id", ondelete="RESTRICT"), nullable=True
    )
    product: Mapped[Product | None] = relationship("Product", lazy="selectin")

    # Additive, same pattern as product_id: category (the fixed enum) stays
    # for backward compatibility. ON DELETE SET NULL (not RESTRICT) because
    # a HouseholdCategory is one home's own label — deleting it should just
    # uncategorize the item, not block the delete or affect other homes.
    # Now the single source of truth for an item's category (issue #43
    # follow-up): the old fixed InventoryCategory enum is gone. RESTRICT
    # because the column is required -- a category in use can't be deleted
    # out from under items that reference it.
    household_category_id: Mapped[HouseholdCategoryId] = mapped_column(
        ForeignKey("household_categories.id", ondelete="RESTRICT"),
        nullable=False,
    )
    household_category: Mapped[HouseholdCategory] = relationship(
        "HouseholdCategory",
        lazy="selectin",
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
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
            "ix_inventory_home_household_category",
            "home_id",
            "household_category_id",
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
