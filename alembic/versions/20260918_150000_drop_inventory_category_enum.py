"""Drop legacy InventoryCategory enum column; household_category_id becomes the
single source of truth for an item's category (issue #43 follow-up).

Backfills a HouseholdCategory row per distinct (home_id, category) pair still
missing one, points every inventory_items row at it, then makes
household_category_id required and drops the old category column/enum.
"""

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "8a1f2c9d4e6b"
down_revision = "f299f451938a"
branch_labels = None
depends_on = None

inventory_items = sa.table(
    "inventory_items",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("home_id", postgresql.UUID(as_uuid=True)),
    sa.column("category", sa.String()),
    sa.column("household_category_id", postgresql.UUID(as_uuid=True)),
)

household_categories = sa.table(
    "household_categories",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("home_id", postgresql.UUID(as_uuid=True)),
    sa.column("name", sa.String()),
)


def upgrade():
    conn = op.get_bind()

    # 1. Backfill: one HouseholdCategory per distinct (home_id, category) pair
    #    that doesn't already have a matching household_categories row.
    distinct_pairs = conn.execute(
        sa.select(inventory_items.c.home_id, inventory_items.c.category)
        .where(inventory_items.c.household_category_id.is_(None))
        .distinct()
    ).all()

    for home_id, category in distinct_pairs:
        if category is None:
            continue

        category_name = category.capitalize()

        existing_id = conn.execute(
            sa.select(household_categories.c.id).where(
                household_categories.c.home_id == home_id,
                household_categories.c.name == category_name,
            )
        ).scalar()

        if existing_id is None:
            existing_id = uuid.uuid4()
            conn.execute(
                household_categories.insert().values(
                    id=existing_id,
                    home_id=home_id,
                    name=category_name,
                )
            )

        conn.execute(
            inventory_items.update()
            .where(
                inventory_items.c.home_id == home_id,
                inventory_items.c.category == category,
                inventory_items.c.household_category_id.is_(None),
            )
            .values(household_category_id=existing_id)
        )

    # 2. Make household_category_id required now that every row has one.
    op.alter_column(
        "inventory_items",
        "household_category_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )

    # 3. Tighten the FK from SET NULL to RESTRICT to match the ORM model.
    op.drop_constraint(
        "fk_inventory_items_household_category_id_household_categories",
        "inventory_items",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_inventory_items_household_category_id_household_categories",
        "inventory_items",
        "household_categories",
        ["household_category_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # 4. Drop the old fixed-enum column, its index, and the enum type itself.
    op.drop_index("ix_inventory_home_category", table_name="inventory_items")
    op.drop_column("inventory_items", "category")
    op.execute("DROP TYPE IF EXISTS inventory_category_enum")


def downgrade():
    op.execute(
        "CREATE TYPE inventory_category_enum AS ENUM "
        "('kitchen', 'bathroom', 'cleaning', 'other')"
    )
    op.add_column(
        "inventory_items",
        sa.Column(
            "category",
            postgresql.ENUM(
                "kitchen",
                "bathroom",
                "cleaning",
                "other",
                name="inventory_category_enum",
                create_type=False,
            ),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_inventory_home_category",
        "inventory_items",
        ["home_id", "category"],
        unique=False,
    )

    conn = op.get_bind()
    rows = conn.execute(
        sa.select(inventory_items.c.id, household_categories.c.name).select_from(
            inventory_items.join(
                household_categories,
                inventory_items.c.household_category_id == household_categories.c.id,
            )
        )
    ).all()
    for item_id, category_name in rows:
        lowered = category_name.lower()
        value = lowered if lowered in ("kitchen", "bathroom", "cleaning") else "other"
        conn.execute(
            inventory_items.update()
            .where(inventory_items.c.id == item_id)
            .values(category=value)
        )

    op.alter_column("inventory_items", "category", nullable=False)

    op.drop_constraint(
        "fk_inventory_items_household_category_id_household_categories",
        "inventory_items",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_inventory_items_household_category_id_household_categories",
        "inventory_items",
        "household_categories",
        ["household_category_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.alter_column(
        "inventory_items",
        "household_category_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )
