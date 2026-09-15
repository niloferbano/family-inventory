"""Add single-use password reset state.

Revision ID: e41b8d9a72c3
Revises: f0fe2980cf32
"""

import sqlalchemy as sa

from alembic import op

revision = "e41b8d9a72c3"
down_revision = "f0fe2980cf32"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users", sa.Column("password_reset_hash", sa.String(64), nullable=True)
    )
    op.add_column(
        "users",
        sa.Column(
            "password_reset_expires_at", sa.DateTime(timezone=True), nullable=True
        ),
    )
    op.create_unique_constraint(
        "uq_users_password_reset_hash", "users", ["password_reset_hash"]
    )


def downgrade():
    op.drop_constraint("uq_users_password_reset_hash", "users", type_="unique")
    op.drop_column("users", "password_reset_expires_at")
    op.drop_column("users", "password_reset_hash")
