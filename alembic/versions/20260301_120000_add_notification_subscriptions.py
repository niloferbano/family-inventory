"""add notification_subscriptions

Revision ID: c8b5f0b1e2aa
Revises: 7b4376594b22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM

from alembic import op

revision: str = "c8b5f0b1e2aa"
down_revision: Union[str, Sequence[str], None] = "7b4376594b22"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # IMPORTANT: reuse existing enum type; do not create it here
    notification_channel_enum = ENUM(
        name="notification_channel_enum",
        create_type=False,
    )

    op.create_table(
        "notification_subscriptions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("home_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("topic", sa.String(length=200), nullable=False),
        sa.Column("channel", notification_channel_enum, nullable=False),
        sa.Column(
            "enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
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
        sa.ForeignKeyConstraint(["home_id"], ["homes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "home_id",
            "user_id",
            "topic",
            "channel",
            name="uq_notification_subscription_target",
        ),
    )

    op.create_index(
        op.f("ix_notification_subscriptions_channel"),
        "notification_subscriptions",
        ["channel"],
    )
    op.create_index(
        op.f("ix_notification_subscriptions_created_at"),
        "notification_subscriptions",
        ["created_at"],
    )
    op.create_index(
        op.f("ix_notification_subscriptions_home_id"),
        "notification_subscriptions",
        ["home_id"],
    )
    op.create_index(
        op.f("ix_notification_subscriptions_updated_at"),
        "notification_subscriptions",
        ["updated_at"],
    )
    op.create_index(
        op.f("ix_notification_subscriptions_user_id"),
        "notification_subscriptions",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_notification_subscriptions_user_id"),
        table_name="notification_subscriptions",
    )
    op.drop_index(
        op.f("ix_notification_subscriptions_updated_at"),
        table_name="notification_subscriptions",
    )
    op.drop_index(
        op.f("ix_notification_subscriptions_home_id"),
        table_name="notification_subscriptions",
    )
    op.drop_index(
        op.f("ix_notification_subscriptions_created_at"),
        table_name="notification_subscriptions",
    )
    op.drop_index(
        op.f("ix_notification_subscriptions_channel"),
        table_name="notification_subscriptions",
    )
    op.drop_table("notification_subscriptions")
