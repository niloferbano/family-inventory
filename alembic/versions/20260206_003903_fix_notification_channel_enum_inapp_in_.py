"""fix notification_channel_enum inapp -> in_app

Revision ID: fcda5edbb7c6
Revises: 51db08e94c9e
Create Date: 2026-02-06 00:39:03.640685

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fcda5edbb7c6"
down_revision: Union[str, Sequence[str], None] = "51db08e94c9e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # 1) create new enum type
    op.execute(
        """
        CREATE TYPE notification_channel_enum_new AS ENUM ('email','sms','push','log','in_app');
    """
    )

    # 2) alter columns using the old enum -> new enum (with mapping)
    op.execute(
        """
        ALTER TABLE notification_subscriptions
        ALTER COLUMN channel TYPE notification_channel_enum_new
        USING (
            CASE
              WHEN channel::text = 'inapp' THEN 'in_app'
              ELSE channel::text
            END
        )::notification_channel_enum_new;
    """
    )

    op.execute(
        """
        ALTER TABLE notification_deliveries
        ALTER COLUMN channel TYPE notification_channel_enum_new
        USING (
            CASE
              WHEN channel::text = 'inapp' THEN 'in_app'
              ELSE channel::text
            END
        )::notification_channel_enum_new;
    """
    )

    # 3) drop old type and rename new
    op.execute("DROP TYPE notification_channel_enum;")
    op.execute(
        "ALTER TYPE notification_channel_enum_new RENAME TO notification_channel_enum;"
    )


def downgrade():
    op.execute(
        """
        CREATE TYPE notification_channel_enum_old AS ENUM ('email','sms','push','log','inapp');
    """
    )

    op.execute(
        """
        ALTER TABLE notification_subscriptions
        ALTER COLUMN channel TYPE notification_channel_enum_old
        USING (
            CASE
              WHEN channel::text = 'in_app' THEN 'inapp'
              ELSE channel::text
            END
        )::notification_channel_enum_old;
    """
    )

    op.execute(
        """
        ALTER TABLE notification_deliveries
        ALTER COLUMN channel TYPE notification_channel_enum_old
        USING (
            CASE
              WHEN channel::text = 'in_app' THEN 'inapp'
              ELSE channel::text
            END
        )::notification_channel_enum_old;
    """
    )

    op.execute("DROP TYPE notification_channel_enum;")
    op.execute(
        "ALTER TYPE notification_channel_enum_old RENAME TO notification_channel_enum;"
    )
