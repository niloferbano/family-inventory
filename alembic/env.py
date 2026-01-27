from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
# IMPORTANT: ensure models are imported so SQLBase.metadata is populated
# Import whichever modules define models:
from app.apis.homes import models as _homes_models  # noqa: F401
from app.apis.homeuser import models as _homeuser_models  # noqa: F401
from app.apis.inventory import models as _inventory_models  # noqa: F401
from app.apis.notifications import \
    models as _notifications_models  # noqa: F401
from app.apis.users import models as _users_models  # noqa: F401
from app.core.configs.config import settings
from app.core.database.base import SQLBase

config = context.config

# logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Use sync URL for Alembic
sync_url = settings.DATABASE_URL.replace("+asyncpg", "")
config.set_main_option("sqlalchemy.url", sync_url)

target_metadata = SQLBase.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
