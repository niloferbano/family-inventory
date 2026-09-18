"""Reconcile notification_deliveries/outbox/in_app_notifications drift.

Cleans up duplicate constraints/indexes left behind by earlier migrations
that added an idempotent, differently-named replacement without dropping the
original (uq_inbox_user_event alongside uq_notification_inbox_event_user;
uq_notification_outbox_event_id alongside the unnamed-turned
notification_outbox_event_id_key; ix_outbox_status_next_retry alongside
ix_notification_outbox_status_next_retry). Also backfills and locks down
notification_deliveries.context, which was added nullable with no default
(20260206_161247) and never tightened, and adds the two indexes the model
declares that were never created (ix_notification_deliveries_event_id,
ix_notification_outbox_next_retry_at).

The inventory_items.product_id index question is intentionally NOT handled
here -- see the separate product_id index decision.

Revision ID: 5db31a5dba5c
Revises: 8a1f2c9d4e6b
Create Date: 2026-09-18 13:18:39.911233

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5db31a5dba5c"
down_revision: Union[str, Sequence[str], None] = "8a1f2c9d4e6b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- in_app_notifications: drop the duplicate unique constraint ----
    # uq_notification_inbox_event_user (2026-02-03) and uq_inbox_user_event
    # (2026-02-05, added idempotently without dropping the first) both
    # enforce UNIQUE(event_id, user_id). The model only declares
    # uq_inbox_user_event, so drop the older duplicate; uniqueness is
    # preserved by the survivor.
    op.drop_constraint(
        op.f("uq_notification_inbox_event_user"), "in_app_notifications", type_="unique"
    )

    # ---- notification_deliveries.context: backfill before tightening ----
    # Added nullable with no server_default (20260206_161247); any row
    # written before the ORM's default=dict/server_default was in effect
    # can still have NULL here. Backfill first or the NOT NULL alter below
    # fails on any such row.
    op.execute(
        "UPDATE notification_deliveries SET context = '{}'::jsonb "
        "WHERE context IS NULL"
    )
    op.alter_column(
        "notification_deliveries",
        "context",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )
    op.create_index(
        op.f("ix_notification_deliveries_event_id"),
        "notification_deliveries",
        ["event_id"],
        unique=False,
    )

    # ---- notification_outbox: drop duplicates, add the missing index ----
    # ix_notification_outbox_status_next_retry (2026-02-08) duplicates
    # ix_outbox_status_next_retry (initial schema), which matches the model
    # and is left in place.
    op.drop_index(
        op.f("ix_notification_outbox_status_next_retry"),
        table_name="notification_outbox",
    )
    # notification_outbox_event_id_key is Postgres's auto-generated name for
    # the unnamed UniqueConstraint("event_id") from the initial schema;
    # uq_notification_outbox_event_id (2026-02-08) duplicates it under an
    # explicit name that matches the model, so the auto-named one is safe
    # to drop.
    op.drop_constraint(
        op.f("notification_outbox_event_id_key"), "notification_outbox", type_="unique"
    )
    # next_retry_at has no standalone index yet; the model declares
    # index=True on it separately from the (status, next_retry_at) composite.
    op.create_index(
        op.f("ix_notification_outbox_next_retry_at"),
        "notification_outbox",
        ["next_retry_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_notification_outbox_next_retry_at"), table_name="notification_outbox"
    )
    op.create_unique_constraint(
        op.f("notification_outbox_event_id_key"),
        "notification_outbox",
        ["event_id"],
    )
    op.create_index(
        op.f("ix_notification_outbox_status_next_retry"),
        "notification_outbox",
        ["status", "next_retry_at"],
        unique=False,
    )
    op.drop_index(
        op.f("ix_notification_deliveries_event_id"),
        table_name="notification_deliveries",
    )
    op.alter_column(
        "notification_deliveries",
        "context",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        nullable=True,
        server_default=None,
    )
    op.create_unique_constraint(
        op.f("uq_notification_inbox_event_user"),
        "in_app_notifications",
        ["event_id", "user_id"],
    )
