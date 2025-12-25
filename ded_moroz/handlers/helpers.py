from __future__ import annotations

from ded_moroz.config import settings
from ded_moroz.db.models import User, UserStatus
from ded_moroz.utils.time import (
    current_campaign_day,
    current_day_deadline,
    is_before_start,
    is_campaign_active,
    is_quiet_hours,
    now,
    quiet_hours_end,
)


def is_admin(telegram_id: int) -> bool:
    return telegram_id in settings.admins.admin_ids


def format_status(user: User) -> str:
    current_dt = now()
    is_enrolled = user.status != UserStatus.STOPPED
    is_paused = user.status == UserStatus.PAUSED
    if is_campaign_active(current_dt):
        campaign_state = "идёт"
    elif is_before_start(current_dt):
        campaign_state = "ещё не началась"
    else:
        campaign_state = "завершилась"
    day = current_campaign_day(current_dt, clamp=True)
    _, deadline_dt = current_day_deadline(current_dt)
    quiet_hours_pause = quiet_hours_end(current_dt) if is_quiet_hours(current_dt) else None

    if is_paused:
        pause_until = "Пауза до возобновления (/resume)"
    elif quiet_hours_pause:
        pause_until = quiet_hours_pause.strftime("%d.%m %H:%M %Z")
    else:
        pause_until = "—"

    lines = [
        f"ID: {user.telegram_id}",
        f"Статус: {user.status.value}",
        f"Записан: {'да' if is_enrolled else 'нет'}",
        f"На паузе: {'да' if is_paused else 'нет'}",
        f"Пауза до: {pause_until}",
        f"Имя: {(user.first_name or '').strip()} {(user.last_name or '').strip()}",
        f"Юзернейм: @{user.username}" if user.username else "Юзернейм: —",
        f"День кампании: {day}/{settings.campaign.days}",
        f"Дедлайн сегодня: {deadline_dt.strftime('%H:%M %Z')}",
        f"Кампания: {campaign_state}",
    ]
    return "\n".join(lines)
