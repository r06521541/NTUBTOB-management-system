from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from shared_lib.shared_module.portal_data.local_database import (
    require_local_database_url,
)
from shared_lib.shared_module.portal_data.models import PortalDataBase

LEGACY_UNMANAGED_TABLES = frozenset(
    {
        "attendance_reply_types",
        "ballparks",
        "cancellations",
        "discord_webhooks",
        "game_attendance_replies",
        "line_groups",
        "line_notify_tokens",
        "line_users",
    }
)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

database_url = require_local_database_url(os.environ.get("PORTAL_DATA_DATABASE_URL"))
config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
target_metadata = PortalDataBase.metadata


def include_object(object_, name, type_, reflected, compare_to):
    """Keep production legacy tables outside portal-data autogenerate ownership."""
    if type_ == "table" and reflected and name in LEGACY_UNMANAGED_TABLES:
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        include_object=include_object,
        version_table_schema="ntubtob",
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
            include_schemas=True,
            include_object=include_object,
            version_table_schema="ntubtob",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
