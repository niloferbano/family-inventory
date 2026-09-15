"""Track the current activation token and its expiration."""

import sqlalchemy as sa

from alembic import op

revision = "b729a13c408e"
down_revision = "e41b8d9a72c3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users", sa.Column("activation_token_hash", sa.String(64), nullable=True)
    )
    op.add_column(
        "users",
        sa.Column("activation_expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_column("users", "activation_expires_at")
    op.drop_column("users", "activation_token_hash")
