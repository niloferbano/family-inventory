"""Add nullable household_category_id link on inventory_items (issue #43 follow-up)."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "f299f451938a"
down_revision = "4304258471a2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "inventory_items",
        sa.Column(
            "household_category_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
    )
    op.create_foreign_key(
        "fk_inventory_items_household_category_id_household_categories",
        "inventory_items",
        "household_categories",
        ["household_category_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_inventory_home_household_category",
        "inventory_items",
        ["home_id", "household_category_id"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_inventory_home_household_category", table_name="inventory_items")
    op.drop_constraint(
        "fk_inventory_items_household_category_id_household_categories",
        "inventory_items",
        type_="foreignkey",
    )
    op.drop_column("inventory_items", "household_category_id")
