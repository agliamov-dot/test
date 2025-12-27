from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ded_moroz.config import settings
from ded_moroz.db.models import AdminErrorQueue, ErrorLog, SeverityLevel
from ded_moroz.db.session import session_scope

logger = logging.getLogger(__name__)


async def log_error(
    level: SeverityLevel, message: str, context: dict[str, Any] | None = None, service_name: str | None = None
) -> ErrorLog:
    async with session_scope() as session:
        record = ErrorLog(level=level, message=message, context=context, service_name=service_name)
        session.add(record)
        await session.flush()

        if level in {SeverityLevel.ERROR, SeverityLevel.CRITICAL}:
            queue_item = AdminErrorQueue(error_log_id=record.id)
            session.add(queue_item)
        return record


async def fetch_recent_errors(
    limit: int = 20, service_name: str | None = None, message_query: str | None = None
) -> list[ErrorLog]:
    async with session_scope() as session:
        query = select(ErrorLog)
        if service_name:
            query = query.where(ErrorLog.service_name == service_name)
        if message_query:
            query = query.where(ErrorLog.message.ilike(f"%{message_query}%"))
        query = query.order_by(ErrorLog.id.desc()).limit(limit)
        result = await session.execute(query)
        return list(result.scalars())


async def fetch_pending_admin_errors(limit: int = 50) -> list[AdminErrorQueue]:
    async with session_scope() as session:
        result = await session.execute(
            select(AdminErrorQueue)
            .options(selectinload(AdminErrorQueue.error))
            .where(AdminErrorQueue.notified.is_(False))
            .order_by(AdminErrorQueue.id.asc())
            .limit(limit)
        )
        return list(result.scalars())


async def mark_admin_error_notified(queue_item: AdminErrorQueue) -> None:
    async with session_scope() as session:
        db_obj = await session.get(AdminErrorQueue, queue_item.id)
        if db_obj:
            db_obj.notified = True
