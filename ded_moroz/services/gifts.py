from __future__ import annotations

from sqlalchemy import select

from ded_moroz.db.models import Gift, GiftType
from ded_moroz.db.session import session_scope


async def get_gift_for_day(day: int) -> Gift | None:
    async with session_scope() as session:
        result = await session.execute(select(Gift).where(Gift.day == day))
        return result.scalar_one_or_none()


async def list_gifts() -> list[Gift]:
    async with session_scope() as session:
        result = await session.execute(select(Gift).order_by(Gift.day))
        return list(result.scalars())


async def set_gift(
    day: int,
    gift_type: GiftType = GiftType.TEXT,
    gift_text: str | None = None,
    gift_url: str | None = None,
    payload: dict | None = None,
) -> Gift:
    async with session_scope() as session:
        result = await session.execute(select(Gift).where(Gift.day == day))
        gift = result.scalar_one_or_none()
        if gift is None:
            gift = Gift(day=day)
            session.add(gift)
        gift.gift_type = gift_type
        gift.gift_text = gift_text
        gift.gift_url = gift_url
        gift.payload = payload
        return gift
