"""add unique inventory name per home

Revision ID: e2ac077a8ac2
Revises: 2b441d703831
Create Date: 2025-12-13 00:52:50.391875

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e2ac077a8ac2"
down_revision: Union[str, Sequence[str], None] = "2b441d703831"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.execute(
        """
    DELETE FROM inventory_items a
    USING inventory_items b
    WHERE a.id > b.id
      AND a.home_id = b.home_id
      AND a.name = b.name;
    """
    )

    op.create_unique_constraint(
        "uq_inventory_home_name",
        "inventory_items",
        ["home_id", "name"],
    )

    op.create_index(
        "ix_inventory_home_created_at",
        "inventory_items",
        ["home_id", "created_at"],
    )

    op.create_index(
        "ix_inventory_home_category",
        "inventory_items",
        ["home_id", "category"],
    )

    op.create_index(
        "ix_inventory_home_expiry",
        "inventory_items",
        ["home_id", "expiry_date"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_inventory_home_name",
        "inventory_items",
        type_="unique",
    )
