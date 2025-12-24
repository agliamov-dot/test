from __future__ import annotations

from ded_moroz.config import settings
from ded_moroz.db.models import User, UserStatus


def is_admin(telegram_id: int) -> bool:
    return telegram_id in settings.admins.admin_ids


def format_status(user: User) -> str:
    lines = [
        f"ID: {user.telegram_id}",
        f"Статус: {user.status.value}",
        f"Имя: {(user.first_name or '').strip()} {(user.last_name or '').strip()}",
        f"Юзернейм: @{user.username}" if user.username else "Юзернейм: —",
    ]
    return "\n".join(lines)
