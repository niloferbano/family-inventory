"""fix notification enums and constraints

Revision ID: 51db08e94c9e
Revises: 1d45a9f7e7ad
Create Date: 2026-02-05 16:11:44.314863

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "51db08e94c9e"
down_revision: Union[str, Sequence[str], None] = "1d45a9f7e7ad"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.execute(
        """
        ALTER TYPE notification_channel_enum RENAME TO notification_channel_enum_old;
    """
    )

    op.execute(
        """
        CREATE TYPE notification_channel_enum AS ENUM (
            'email',
            'sms',
            'push',
            'log',
            'in_app'
        );
    """
    )

    # Update all columns using the enum
    for table, column in [
        ("notification_deliveries", "channel"),
        ("notification_subscriptions", "channel"),
    ]:
        op.execute(
            f"""
            ALTER TABLE {table}
            ALTER COLUMN {column}
            TYPE notification_channel_enum
            USING REPLACE({column}::text, 'inapp', 'in_app')::notification_channel_enum;
        """
        )

    op.execute("DROP TYPE notification_channel_enum_old;")

    # ---- 2. Drop accidental unique constraint on event_id (if present) ----
    op.execute(
        """
        ALTER TABLE notification_deliveries
        DROP CONSTRAINT IF EXISTS notification_deliveries_event_id_key;
        """
    )

    # ---- 3. Ensure correct unique constraints (idempotent) ----
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'uq_delivery_per_target'
            ) THEN
                ALTER TABLE notification_deliveries
                ADD CONSTRAINT uq_delivery_per_target
                UNIQUE (event_id, channel, recipient_type, recipient);
            END IF;
        END $$;
        """
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'uq_inbox_user_event'
            ) THEN
                ALTER TABLE in_app_notifications
                ADD CONSTRAINT uq_inbox_user_event
                UNIQUE (event_id, user_id);
            END IF;
        END $$;
        """
    )


def downgrade():
    raise RuntimeError("Downgrade not supported for notification enum migration")
