"""add inventory items table

Revision ID: 2b441d703831
Revises: 
Create Date: 2025-12-12 00:28:37.312511

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2b441d703831"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():

    op.create_table(
        "inventory_items",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column(
            "home_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("homes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column(
            "category",
            sa.Enum(
                "kitchen",
                "bathroom",
                "cleaning",
                "other",
                name="inventory_category_enum",
            ),
            nullable=False,
        ),
        sa.Column("quantity", sa.Integer(), server_default="1", nullable=False),
        sa.Column("unit", sa.String(length=30), server_default="pcs", nullable=False),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )

    op.create_index("ix_inventory_items_home_id", "inventory_items", ["home_id"])
    op.create_index("ix_inventory_items_created_by", "inventory_items", ["created_by"])
    op.create_index("ix_inventory_items_category", "inventory_items", ["category"])


def downgrade():
    op.drop_index("ix_inventory_items_category", table_name="inventory_items")
    op.drop_index("ix_inventory_items_created_by", table_name="inventory_items")
    op.drop_index("ix_inventory_items_home_id", table_name="inventory_items")

    op.drop_table("inventory_items")
