from __future__ import annotations

from sqlalchemy import select

from ded_moroz.db.models import User, UserStatus
from ded_moroz.db.session import session_scope


async def get_or_create_user(telegram_id: int, username: str | None, first_name: str | None, last_name: str | None) -> User:
    async with session_scope() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if user is None:
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                status=UserStatus.ACTIVE,
            )
            session.add(user)
        else:
            user.username = username
            user.first_name = first_name
            user.last_name = last_name
        return user


async def update_status(user_id: int, status: UserStatus) -> None:
    async with session_scope() as session:
        user = await session.get(User, user_id)
        if user:
            user.status = status


async def get_user_by_telegram(telegram_id: int) -> User | None:
    async with session_scope() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        return result.scalar_one_or_none()


async def list_active_users(limit: int, offset: int = 0) -> list[User]:
    async with session_scope() as session:
        result = await session.execute(
            select(User).where(User.status == UserStatus.ACTIVE).order_by(User.id.asc()).limit(limit).offset(offset)
        )
        return list(result.scalars())
