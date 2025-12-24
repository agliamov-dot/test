from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from ded_moroz.db.models import ServiceHeartbeat
from ded_moroz.db.session import session_scope


async def beat(service_name: str) -> ServiceHeartbeat:
    async with session_scope() as session:
        result = await session.execute(select(ServiceHeartbeat).where(ServiceHeartbeat.service_name == service_name))
        heartbeat = result.scalar_one_or_none()
        if heartbeat is None:
            heartbeat = ServiceHeartbeat(service_name=service_name, last_beat_at=datetime.utcnow())
            session.add(heartbeat)
        else:
            heartbeat.last_beat_at = datetime.utcnow()
        return heartbeat
