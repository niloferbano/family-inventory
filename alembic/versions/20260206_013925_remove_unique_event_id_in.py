"""remove unique event_id in

Revision ID: dc551d523164
Revises: fcda5edbb7c6
Create Date: 2026-02-06 01:39:25.901052

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "dc551d523164"
down_revision: Union[str, Sequence[str], None] = "fcda5edbb7c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.drop_index(
        "ix_notification_deliveries_event_id", table_name="notification_deliveries"
    )


def downgrade():
    op.create_index(
        "ix_notification_deliveries_event_id",
        "notification_deliveries",
        ["event_id"],
        unique=True,
    )
