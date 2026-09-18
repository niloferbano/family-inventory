"""Data-migration test for issue #44: backfill inventory_items.product_id.

Runs Alembic up to just before the backfill migration, seeds inventory_items
rows directly with raw SQL (a same-name item in two different homes, plus a
name that happens to match a pre-existing catalog Product, plus a row that
already has a product_id), upgrades through the backfill, and asserts it
creates exactly one new Product per row that needed one -- never merging on
name, even when names collide.
"""

import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from alembic import command
from alembic.config import Config
from app.core.configs.config import settings

PRE_BACKFILL_REVISION = "5db31a5dba5c"
BACKFILL_REVISION = "c47e9f21a6b8"


def _with_search_path(db_url: str, schema: str) -> str:
    # Avoid percent-encoding to keep Alembic's config parser happy.
    joiner = "&" if "?" in db_url else "?"
    return f"{db_url}{joiner}options=-csearch_path={schema},public"


def _can_connect(db_url: str) -> bool:
    engine = create_engine(db_url, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except (OperationalError, OSError, PermissionError):
        return False
    finally:
        engine.dispose()


def test_backfill_creates_one_product_per_item_never_merging_on_name(monkeypatch):
    sync_db_url = settings.TEST_DATABASE_URL.replace("+asyncpg", "")
    if not _can_connect(sync_db_url):
        if os.getenv("REQUIRE_TEST_DATABASE") == "true":
            pytest.fail("Required test database unavailable for Alembic migration test")
        pytest.skip("Test database unavailable for Alembic migration test")

    schema = f"alembic_test_{uuid.uuid4().hex}"
    engine = create_engine(sync_db_url, pool_pre_ping=True)
    try:
        with engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))

        async_db_url = _with_search_path(settings.TEST_DATABASE_URL, schema)
        monkeypatch.setattr(settings, "DATABASE_URL", async_db_url)

        alembic_ini = Path(__file__).resolve().parents[2] / "alembic.ini"
        alembic_cfg = Config(str(alembic_ini))

        command.upgrade(alembic_cfg, PRE_BACKFILL_REVISION)

        home_a = uuid.uuid4()
        home_b = uuid.uuid4()
        home_c = uuid.uuid4()
        category_a = uuid.uuid4()
        category_b = uuid.uuid4()
        category_c = uuid.uuid4()
        preexisting_product_id = uuid.uuid4()  # catalog Product("Milk"), pre-existing

        item_a_milk = uuid.uuid4()  # home_a, name="Milk" -- name collides with...
        item_b_milk = uuid.uuid4()  # home_b, name="Milk" -- ...both this row...
        item_c_already_linked = uuid.uuid4()  # ...and this pre-existing Product,
        # none of which should be merged together. item_c lives in its own
        # home_c -- (home_id, name) is still uniquely constrained at this
        # revision (uq_inventory_home_name is only dropped by issue #48), so
        # it can't share home_a's "Milk" row without a real collision.

        with engine.begin() as conn:
            conn.execute(text(f'SET search_path TO "{schema}", public'))

            conn.execute(
                text("INSERT INTO homes (id, name) VALUES (:id, :name)"),
                [
                    {"id": str(home_a), "name": "Backfill Home A"},
                    {"id": str(home_b), "name": "Backfill Home B"},
                    {"id": str(home_c), "name": "Backfill Home C"},
                ],
            )
            conn.execute(
                text(
                    "INSERT INTO household_categories (id, home_id, name) "
                    "VALUES (:id, :home_id, :name)"
                ),
                [
                    {"id": str(category_a), "home_id": str(home_a), "name": "Kitchen"},
                    {"id": str(category_b), "home_id": str(home_b), "name": "Kitchen"},
                    {"id": str(category_c), "home_id": str(home_c), "name": "Kitchen"},
                ],
            )
            conn.execute(
                text(
                    "INSERT INTO inventory_products (id, name, is_active) "
                    "VALUES (:id, :name, true)"
                ),
                {"id": str(preexisting_product_id), "name": "Milk"},
            )
            conn.execute(
                text(
                    "INSERT INTO inventory_items "
                    "(id, home_id, household_category_id, name, product_id, "
                    "quantity, unit) "
                    "VALUES (:id, :home_id, :category_id, :name, :product_id, "
                    "1, 'pcs')"
                ),
                [
                    {
                        "id": str(item_a_milk),
                        "home_id": str(home_a),
                        "category_id": str(category_a),
                        "name": "Milk",
                        "product_id": None,
                    },
                    {
                        "id": str(item_b_milk),
                        "home_id": str(home_b),
                        "category_id": str(category_b),
                        "name": "Milk",
                        "product_id": None,
                    },
                    {
                        # Already has a product_id -- must be left untouched,
                        # not re-pointed at a new or existing "Milk" product.
                        "id": str(item_c_already_linked),
                        "home_id": str(home_c),
                        "category_id": str(category_c),
                        "name": "Milk",
                        "product_id": str(preexisting_product_id),
                    },
                ],
            )

        command.upgrade(alembic_cfg, BACKFILL_REVISION)

        with engine.connect() as conn:
            conn.execute(text(f'SET search_path TO "{schema}", public'))
            items = {
                row["id"]: row
                for row in conn.execute(
                    text("SELECT id, name, product_id FROM inventory_items")
                ).mappings()
            }
            products = {
                row["id"]: row
                for row in conn.execute(
                    text("SELECT id, name, barcode FROM inventory_products")
                ).mappings()
            }

        # Every row now has a product_id.
        assert all(row["product_id"] is not None for row in items.values())

        # The already-linked row was left exactly as it was.
        assert items[item_c_already_linked]["product_id"] == preexisting_product_id

        # The two orphaned "Milk" rows got two DIFFERENT, brand-new products --
        # never merged with each other, and never merged with the
        # pre-existing "Milk" product either, despite the identical name.
        product_a = items[item_a_milk]["product_id"]
        product_b = items[item_b_milk]["product_id"]
        assert product_a != product_b
        assert product_a != preexisting_product_id
        assert product_b != preexisting_product_id

        # Each new product carries the legacy name verbatim, with no barcode.
        assert products[product_a]["name"] == "Milk"
        assert products[product_a]["barcode"] is None
        assert products[product_b]["name"] == "Milk"
        assert products[product_b]["barcode"] is None

        # Exactly one new product per orphaned row: the pre-existing one,
        # plus one for item_a and one for item_b.
        assert len(products) == 3
    finally:
        with engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()
