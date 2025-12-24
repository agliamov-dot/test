from __future__ import annotations

from aiogram import Bot

from ded_moroz.config import settings
from ded_moroz.db.models import NotificationType, SeverityLevel
from ded_moroz.services import submissions as submissions_service
from ded_moroz.services.heartbeat import beat
from ded_moroz.services.logging import log_error
from ded_moroz.services.users import list_active_users
from ded_moroz.utils.time import current_campaign_day, is_campaign_active, missed_window, reminder_window


async def send_daily_reminders(bot: Bot) -> None:
    if not is_campaign_active() or not reminder_window():
        return
    day = current_campaign_day()
    offset = 0
    while True:
        users = await list_active_users(settings.service.chunk_size, offset)
        if not users:
            break
        for user in users:
            already = await submissions_service.has_submission(user.id, day)
            if already:
                continue
            created = await submissions_service.create_notification_log(user.id, day, NotificationType.REMINDER)
            if not created:
                continue
            try:
                await bot.send_message(user.telegram_id, f"День {day}! Не забудь прислать стих для подарка.")
            except Exception as exc:  # noqa: BLE001
                await log_error(SeverityLevel.ERROR, "Failed to send reminder", {"user_id": user.id, "error": str(exc)})
        offset += len(users)
    await beat("scheduler")


async def send_missed_notifications(bot: Bot) -> None:
    if not is_campaign_active() or not missed_window():
        return
    day = current_campaign_day()
    previous_day = day - 1
    if previous_day < 1:
        return

    offset = 0
    while True:
        users = await list_active_users(settings.service.chunk_size, offset)
        if not users:
            break
        for user in users:
            already = await submissions_service.has_submission(user.id, previous_day)
            if already:
                continue
            created = await submissions_service.create_notification_log(
                user.id, previous_day, NotificationType.MISSED
            )
            if not created:
                continue
            try:
                await bot.send_message(
                    user.telegram_id,
                    f"Ты пропустил день {previous_day}. Стих не пришёл. Завтра постарайся не забыть!",
                )
            except Exception as exc:  # noqa: BLE001
                await log_error(
                    SeverityLevel.ERROR,
                    "Failed to send missed notification",
                    {"user_id": user.id, "error": str(exc)},
                )
        offset += len(users)
    await beat("scheduler")
