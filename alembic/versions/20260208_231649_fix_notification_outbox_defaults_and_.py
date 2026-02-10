"""fix notification_outbox defaults and constraints

Revision ID: f0fe2980cf32
Revises: c125cf5990e3
Create Date: 2026-02-08 23:16:49.112414

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f0fe2980cf32"
down_revision: Union[str, Sequence[str], None] = "c125cf5990e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # ---- defaults ----
    op.alter_column(
        "notification_outbox",
        "headers",
        server_default=sa.text("'{}'::jsonb"),
        existing_type=postgresql.JSONB(),
    )

    op.alter_column(
        "notification_outbox",
        "status",
        server_default="PENDING",
        existing_type=sa.String(length=20),
    )

    op.alter_column(
        "notification_outbox",
        "attempt_count",
        server_default="0",
        existing_type=sa.Integer(),
    )

    # ---- constraints ----
    op.create_unique_constraint(
        "uq_notification_outbox_event_id",
        "notification_outbox",
        ["event_id"],
    )

    # ---- indexes ----
    op.create_index(
        "ix_notification_outbox_event_id",
        "notification_outbox",
        ["event_id"],
    )

    op.create_index(
        "ix_notification_outbox_status_next_retry",
        "notification_outbox",
        ["status", "next_retry_at"],
    )


def downgrade():
    op.drop_index(
        "ix_notification_outbox_status_next_retry", table_name="notification_outbox"
    )
    op.drop_index("ix_notification_outbox_event_id", table_name="notification_outbox")

    op.drop_constraint(
        "uq_notification_outbox_event_id",
        "notification_outbox",
        type_="unique",
    )

    op.alter_column(
        "notification_outbox",
        "headers",
        server_default=None,
    )
    op.alter_column(
        "notification_outbox",
        "status",
        server_default=None,
    )
    op.alter_column(
        "notification_outbox",
        "attempt_count",
        server_default=None,
    )
