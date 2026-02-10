"""add context to NotificationDelivery

Revision ID: c125cf5990e3
Revises: dc551d523164
Create Date: 2026-02-06 16:12:47.875670

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c125cf5990e3"
down_revision: Union[str, Sequence[str], None] = "dc551d523164"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("notification_deliveries") as batch:
        batch.add_column(
            sa.Column(
                "context",
                sa.dialects.postgresql.JSONB(),
                nullable=True,
            )
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("notification_deliveries") as batch:
        batch.drop_column("context")
