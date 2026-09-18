"""Add inventory_products table (Product/StockBatch refactor, issue #42)."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "702177ab7626"
down_revision = "b729a13c408e"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "inventory_products",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("barcode", sa.String(length=64), nullable=True),
        sa.Column("brand", sa.String(length=100), nullable=True),
        sa.Column("external_category", sa.String(length=100), nullable=True),
        sa.Column("image_url", sa.String(length=500), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_product_barcode_unique",
        "inventory_products",
        ["barcode"],
        unique=True,
        postgresql_where=sa.text("barcode IS NOT NULL"),
    )
    op.create_index("ix_product_name", "inventory_products", ["name"], unique=False)
    op.create_index(
        "ix_product_is_active", "inventory_products", ["is_active"], unique=False
    )
    op.create_index(
        op.f("ix_inventory_products_created_at"),
        "inventory_products",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_inventory_products_updated_at"),
        "inventory_products",
        ["updated_at"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        op.f("ix_inventory_products_updated_at"), table_name="inventory_products"
    )
    op.drop_index(
        op.f("ix_inventory_products_created_at"), table_name="inventory_products"
    )
    op.drop_index("ix_product_is_active", table_name="inventory_products")
    op.drop_index("ix_product_name", table_name="inventory_products")
    op.drop_index("ix_product_barcode_unique", table_name="inventory_products")
    op.drop_table("inventory_products")
