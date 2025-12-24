from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from ded_moroz.db.models import ServiceHeartbeat
from ded_moroz.db.session import session_scope


async def beat(service_name: str, interval_seconds: int | None = None) -> ServiceHeartbeat:
    async with session_scope() as session:
        result = await session.execute(select(ServiceHeartbeat).where(ServiceHeartbeat.service_name == service_name))
        heartbeat = result.scalar_one_or_none()
        if heartbeat is None:
            heartbeat = ServiceHeartbeat(
                service_name=service_name,
                last_beat_at=datetime.now(timezone.utc),
                beat_interval_seconds=interval_seconds or 600,
            )
            session.add(heartbeat)
        else:
            heartbeat.last_beat_at = datetime.now(timezone.utc)
            if interval_seconds is not None:
                heartbeat.beat_interval_seconds = interval_seconds
        return heartbeat
