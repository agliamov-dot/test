from __future__ import annotations

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from ded_moroz.config import settings
from ded_moroz.db.models import NotificationType, SeverityLevel
from ded_moroz.services import submissions as submissions_service
from ded_moroz.services.heartbeat import beat
from ded_moroz.services.logging import log_error
from ded_moroz.services.users import list_active_users
from ded_moroz.utils.time import (
    current_campaign_day,
    day_deadline,
    is_after_deadline,
    is_campaign_active,
    is_quiet_hours,
    missed_window,
    reminder_window,
)


def _notification_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Сдать стих", callback_data="gift:submit")],
            [InlineKeyboardButton(text="Пауза", callback_data="user:pause")],
        ]
    )


async def send_daily_reminders(bot: Bot) -> None:
    if not is_campaign_active() or not reminder_window() or is_quiet_hours() or is_after_deadline():
        return
    day = current_campaign_day()
    offset = 0
    while True:
        users = await list_active_users(settings.service.chunk_size, offset)
        if not users:
            break
        user_ids = [user.id for user in users]
        submitted_ids = await submissions_service.get_submissions_for_users(user_ids, day)
        pending_users = [user for user in users if user.id not in submitted_ids]
        created_ids = await submissions_service.create_notification_logs_batch(
            [user.id for user in pending_users], day, NotificationType.REMINDER
        )
        if not created_ids:
            offset += len(users)
            continue

        deadline = day_deadline(day).strftime("%H:%M %Z")
        keyboard = _notification_keyboard()
        for user in pending_users:
            if user.id not in created_ids:
                continue
            try:
                await bot.send_message(
                    user.telegram_id,
                    f"День {day}! Не забудь прислать стих до {deadline}, чтобы получить подарок.",
                    reply_markup=keyboard,
                )
            except Exception as exc:  # noqa: BLE001
                await log_error(
                    SeverityLevel.ERROR,
                    "Failed to send reminder",
                    {"user_id": user.id, "error": str(exc)},
                    service_name="scheduler",
                )
        offset += len(users)
    await beat("scheduler", interval_seconds=24 * 60 * 60)


async def send_missed_notifications(bot: Bot) -> None:
    if not is_campaign_active() or not missed_window() or is_quiet_hours():
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
        user_ids = [user.id for user in users]
        submitted_ids = await submissions_service.get_submissions_for_users(user_ids, previous_day)
        pending_users = [user for user in users if user.id not in submitted_ids]
        created_ids = await submissions_service.create_notification_logs_batch(
            [user.id for user in pending_users], previous_day, NotificationType.MISSED
        )
        if not created_ids:
            offset += len(users)
            continue

        yesterday_deadline = day_deadline(previous_day).strftime("%H:%M %Z")
        today_deadline = day_deadline(day).strftime("%H:%M %Z")
        keyboard = _notification_keyboard()
        for user in pending_users:
            if user.id not in created_ids:
                continue
            try:
                await bot.send_message(
                    user.telegram_id,
                    (
                        f"Ты пропустил день {previous_day} — дедлайн был {yesterday_deadline}. "
                        f"Сегодня дедлайн в {today_deadline}, не забудь прислать стих!"
                    ),
                    reply_markup=keyboard,
                )
            except Exception as exc:  # noqa: BLE001
                await log_error(
                    SeverityLevel.ERROR,
                    "Failed to send missed notification",
                    {"user_id": user.id, "error": str(exc)},
                    service_name="scheduler",
                )
        offset += len(users)
    await beat("scheduler", interval_seconds=24 * 60 * 60)
