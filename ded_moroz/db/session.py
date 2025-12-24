from __future__ import annotations

from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from ded_moroz.config import settings

_engine: AsyncEngine | None = None
_SessionFactory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        connect_args: dict[str, object] = {}
        engine_kwargs: dict[str, object] = {}
        if settings.database.url.startswith("sqlite+") and ":memory:" in settings.database.url:
            engine_kwargs["poolclass"] = StaticPool
            connect_args["check_same_thread"] = False
        _engine = create_async_engine(
            settings.database.url, future=True, connect_args=connect_args, **engine_kwargs
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _SessionFactory


@asynccontextmanager
async def session_scope() -> AsyncSession:
    session_factory = get_session_factory()
    session = session_factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
