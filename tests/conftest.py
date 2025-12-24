from __future__ import annotations

import importlib
import os

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

# Set environment before importing application modules
os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("CAMPAIGN_START_DATE", "2024-12-01")
os.environ.setdefault("CAMPAIGN_TOTAL_DAYS", "24")
os.environ.setdefault("CAMPAIGN_REMINDER_HOUR", "8")
os.environ.setdefault("CAMPAIGN_MISSED_HOUR", "22")
os.environ.setdefault("CAMPAIGN_MAX_ATTEMPTS_PER_DAY", "3")
os.environ.setdefault("ADMIN_IDS", "1")
os.environ.setdefault("BATCH_CHUNK_SIZE", "10")

import ded_moroz.config as config

importlib.reload(config)


# Единый event loop на всю сессию, чтобы asyncpg/SQLAlchemy не конфликтовали
@pytest.fixture(scope="session")
def event_loop():
    import asyncio

    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
async def engine(event_loop) -> AsyncEngine:
    import ded_moroz.db.session as db_session
    from ded_moroz.db.models import Base

    # reset engine cache
    db_session._engine = None
    db_session._SessionFactory = None
    engine = db_session.get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()
