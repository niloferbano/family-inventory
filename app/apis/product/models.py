from __future__ import annotations

from uuid import uuid4

from sqlalchemy import Boolean, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import ProductId, SQLBase, TimeStampMixin


class Product(SQLBase, TimeStampMixin):
    """Shared/global product catalog entry.

    Not home-scoped: a barcode identifies the same physical product for every
    household, so per-home copies would just duplicate catalog data. Products
    with no barcode are still fine to live here — they're simply unshared,
    home-specific entries with no dedup guarantee.
    """

    __tablename__ = "inventory_products"

    id: Mapped[ProductId] = mapped_column(primary_key=True, default=uuid4)

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    barcode: Mapped[str | None] = mapped_column(String(64), nullable=True)
    brand: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Free-text / catalog-provided category, distinct from a household's own
    # InventoryItem.category (kitchen/bathroom/cleaning/other) — external
    # taxonomies won't map cleanly onto that fixed enum.
    external_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Soft-delete: a discontinued/duplicate product is deactivated, never hard
    # deleted while InventoryItem rows still reference it (see the FK's
    # ON DELETE RESTRICT). Inactive products are excluded from search/lookup
    # but stay resolvable for existing inventory items' history.
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )

    __table_args__ = (
        Index(
            "ix_product_barcode_unique",
            "barcode",
            unique=True,
            postgresql_where=text("barcode IS NOT NULL"),
        ),
        Index("ix_product_name", "name"),
        Index("ix_product_is_active", "is_active"),
    )
