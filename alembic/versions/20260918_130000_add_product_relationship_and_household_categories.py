"""Add nullable product_id to inventory_items + household_categories table (issue #43)."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "4304258471a2"
down_revision = "702177ab7626"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "inventory_items",
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_inventory_items_product_id_inventory_products",
        "inventory_items",
        "inventory_products",
        ["product_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        op.f("ix_inventory_items_product_id"),
        "inventory_items",
        ["product_id"],
        unique=False,
    )

    op.create_table(
        "household_categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "home_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("homes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=60), nullable=False),
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
        sa.UniqueConstraint("home_id", "name", name="uq_household_category_home_name"),
    )
    op.create_index("ix_household_category_home", "household_categories", ["home_id"])
    op.create_index(
        op.f("ix_household_categories_created_at"),
        "household_categories",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_household_categories_updated_at"),
        "household_categories",
        ["updated_at"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        op.f("ix_household_categories_updated_at"),
        table_name="household_categories",
    )
    op.drop_index(
        op.f("ix_household_categories_created_at"),
        table_name="household_categories",
    )
    op.drop_index("ix_household_category_home", table_name="household_categories")
    op.drop_table("household_categories")

    op.drop_index(op.f("ix_inventory_items_product_id"), table_name="inventory_items")
    op.drop_constraint(
        "fk_inventory_items_product_id_inventory_products",
        "inventory_items",
        type_="foreignkey",
    )
    op.drop_column("inventory_items", "product_id")
