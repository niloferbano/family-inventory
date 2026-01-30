"""add subscription target

Revision ID: d3a7c1f6b4c0
Revises: c8b5f0b1e2aa
Create Date: 2026-03-01 12:10:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d3a7c1f6b4c0"
down_revision: Union[str, Sequence[str], None] = "c8b5f0b1e2aa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "notification_subscriptions",
        sa.Column(
            "target",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("notification_subscriptions", "target")
