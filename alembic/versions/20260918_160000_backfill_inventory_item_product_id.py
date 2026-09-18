"""Backfill inventory_items.product_id from legacy InventoryItem.name (issue #44).

Creates exactly one Product per existing inventory_items row that doesn't
already have a product_id, using that row's old name verbatim
(Product.barcode left NULL -- legacy rows carry no barcode data at all).
Rows that already have a product_id are left untouched.

Deliberately NOT deduped by name, even across homes:

    InventoryItem A (home=1, name="Milk") -> Product A (name="Milk", barcode=NULL)
    InventoryItem B (home=2, name="Milk") -> Product B (name="Milk", barcode=NULL)

A normalized product name is not a global product identity -- two "Milk"
entries typed by two different households are not verifiably the same
real-world product (different brand, size, store...). Only a real identity
signal (a barcode) can safely merge catalog rows; free-text names can't, so
this migration never merges on name, whether between two legacy rows or
against a pre-existing catalog Product that happens to share a name. This
also makes the migration trivially deterministic and idempotent: each
row's outcome depends only on itself, in a fixed row order, never on scan
order or on what other rows happen to be present.

This is a pure data migration (issue #44 only): product_id stays nullable
and InventoryItem.name stays in place. Making product_id required and
dropping name is a separate, later ticket.

Revision ID: c47e9f21a6b8
Revises: 5db31a5dba5c
Create Date: 2026-09-18 16:00:00.000000

"""

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "c47e9f21a6b8"
down_revision = "5db31a5dba5c"
branch_labels = None
depends_on = None

inventory_items = sa.table(
    "inventory_items",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("name", sa.String()),
    sa.column("product_id", postgresql.UUID(as_uuid=True)),
)

inventory_products = sa.table(
    "inventory_products",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("name", sa.String()),
    sa.column("barcode", sa.String()),
    sa.column("is_active", sa.Boolean()),
    sa.column("created_at", sa.DateTime(timezone=True)),
    sa.column("updated_at", sa.DateTime(timezone=True)),
)


def upgrade():
    # NOTE: ix_inventory_items_product_id is created by 4304258471a2
    # (the migration that first added this column) and never dropped in
    # between -- this migration only backfills data, it does not touch
    # that index.
    conn = op.get_bind()

    rows = conn.execute(
        sa.select(inventory_items.c.id, inventory_items.c.name)
        .where(inventory_items.c.product_id.is_(None))
        .order_by(inventory_items.c.id)
    ).all()

    if not rows:
        return

    now = datetime.now(timezone.utc)

    for item_id, name in rows:
        product_id = uuid.uuid4()
        conn.execute(
            inventory_products.insert().values(
                id=product_id,
                name=name,
                barcode=None,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
        )
        conn.execute(
            inventory_items.update()
            .where(inventory_items.c.id == item_id)
            .values(product_id=product_id)
        )


def downgrade():
    # Data-only backfill: reversing it would mean guessing which
    # product_id assignments predate this migration vs. were made by real
    # usage afterward. Not supported.
    raise RuntimeError("Downgrade not supported for inventory product_id backfill")
