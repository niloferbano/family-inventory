"""add inapp notification channel

Revision ID: 3084df5c4324
Revises: d3a7c1f6b4c0
Create Date: 2026-02-02 14:43:04.776612

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3084df5c4324"
down_revision: Union[str, Sequence[str], None] = "d3a7c1f6b4c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE notification_channel_enum ADD VALUE IF NOT EXISTS 'in_app'")


def downgrade() -> None:
    """Downgrade schema."""
    pass
