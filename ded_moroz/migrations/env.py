from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from ded_moroz.config import settings
from ded_moroz.db.models import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    return settings.database.url


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = get_url()

    def _configure(connection) -> None:
        context.configure(connection=connection, target_metadata=target_metadata)

    def _run_sync_migrations(connection) -> None:
        _configure(connection)
        with context.begin_transaction():
            context.run_migrations()

    if url.startswith("postgresql+asyncpg"):
        connectable: AsyncEngine = create_async_engine(url, poolclass=pool.NullPool)

        async def _run_async_migrations() -> None:
            async with connectable.begin() as connection:
                await connection.run_sync(_run_sync_migrations)
            await connectable.dispose()

        import asyncio

        asyncio.run(_run_async_migrations())
    else:
        connectable = engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
            url=url,
        )

        with connectable.connect() as connection:
            _run_sync_migrations(connection)


def run_migrations() -> None:
    if context.is_offline_mode():
        run_migrations_offline()
    else:
        run_migrations_online()


run_migrations()
