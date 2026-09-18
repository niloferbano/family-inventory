from uuid import uuid4

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import HomeId, HouseholdCategoryId, SQLBase, TimeStampMixin


class HouseholdCategory(SQLBase, TimeStampMixin):
    """A home-defined category for organizing inventory items.

    Replaces growing InventoryCategory (a fixed enum) every time a household
    wants a new bucket (Electronics, Garden, Tools, ...). Each home manages
    its own list; InventoryItem.category stays as-is for now for backward
    compatibility (issue #43) and gets wired to this table in a later ticket.
    """

    __tablename__ = "household_categories"

    id: Mapped[HouseholdCategoryId] = mapped_column(primary_key=True, default=uuid4)
    home_id: Mapped[HomeId] = mapped_column(
        ForeignKey("homes.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(60), nullable=False)

    __table_args__ = (
        UniqueConstraint("home_id", "name", name="uq_household_category_home_name"),
        Index("ix_household_category_home", "home_id"),
    )
