from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.apis.product.models import Product
from app.core.database.base import ProductId


class ProductRepository:
    """Repository for the shared/global product catalog.

    Unlike InventoryRepository, this is not home-scoped: Product rows are
    shared across every home (see Product's docstring for why).
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, product: Product) -> Product:
        self.session.add(product)
        await self.session.flush()
        await self.session.refresh(product)
        return product

    async def get_many(
        self, product_ids: set[ProductId], *, include_inactive: bool = False
    ) -> list[Product]:
        """Bulk existence check, e.g. validating a batch of InventoryItem writes."""
        if not product_ids:
            return []
        stmt = sa.select(Product).where(Product.id.in_(product_ids))
        if not include_inactive:
            stmt = stmt.where(Product.is_active.is_(True))
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_by_id(
        self, product_id: ProductId, *, include_inactive: bool = False
    ) -> Product | None:
        product = await self.session.get(Product, product_id)
        if product is None:
            return None
        if not include_inactive and not product.is_active:
            return None
        return product

    async def get_by_barcode(
        self, barcode: str, *, include_inactive: bool = False
    ) -> Product | None:
        stmt = sa.select(Product).where(Product.barcode == barcode)
        if not include_inactive:
            stmt = stmt.where(Product.is_active.is_(True))
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def find_or_create_by_barcode(
        self,
        *,
        barcode: str,
        name: str,
        brand: str | None = None,
        external_category: str | None = None,
        image_url: str | None = None,
    ) -> tuple[Product, bool]:
        """Idempotently resolve a Product for a barcode.

        Returns (product, created). Two concurrent callers scanning the same
        barcode for the first time race safely: the loser's insert is a no-op
        (ON CONFLICT DO NOTHING on the partial unique barcode index) and it
        falls back to selecting the winner's row, mirroring
        NotificationOutboxRepository.ensure().
        """
        insert_stmt = (
            pg_insert(Product)
            .values(
                name=name,
                barcode=barcode,
                brand=brand,
                external_category=external_category,
                image_url=image_url,
            )
            .on_conflict_do_nothing(
                index_elements=[Product.barcode],
                # Must match the partial unique index's predicate
                # (ix_product_barcode_unique) or Postgres can't infer
                # it as the ON CONFLICT arbiter.
                index_where=sa.text("barcode IS NOT NULL"),
            )
            .returning(Product)
        )
        inserted = (await self.session.execute(insert_stmt)).scalar_one_or_none()
        if inserted is not None:
            return inserted, True

        existing = await self.get_by_barcode(barcode, include_inactive=True)
        if existing is None:
            # Extremely unlikely (race + rollback). Treat as retryable.
            raise RuntimeError(
                f"Product row missing after insert/select for barcode={barcode}"
            )
        return existing, False

    async def search_by_name(
        self,
        query: str,
        *,
        limit: int = 20,
        include_inactive: bool = False,
    ) -> list[Product]:
        stmt = sa.select(Product).where(Product.name.ilike(f"%{query}%"))
        if not include_inactive:
            stmt = stmt.where(Product.is_active.is_(True))
        stmt = stmt.order_by(Product.name.asc()).limit(limit)
        return list((await self.session.execute(stmt)).scalars().all())

    async def deactivate(self, product: Product) -> None:
        product.is_active = False
        await self.session.flush()

    async def reactivate(self, product: Product) -> None:
        product.is_active = True
        await self.session.flush()
