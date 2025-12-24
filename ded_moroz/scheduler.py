from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from ded_moroz.config import settings
from ded_moroz.services.admin_notifications import dispatch_admin_errors
from ded_moroz.services.notifications import send_daily_reminders, send_missed_notifications
from ded_moroz.services.heartbeat import beat

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def reminder_job(bot: Bot) -> None:
    await send_daily_reminders(bot)


async def missed_job(bot: Bot) -> None:
    await send_missed_notifications(bot)


async def heartbeat_job() -> None:
    await beat("scheduler", interval_seconds=600)


async def main() -> None:
    bot = Bot(token=settings.service.bot_token)
    scheduler = AsyncIOScheduler(timezone=settings.campaign.timezone)
    scheduler.add_job(
        reminder_job,
        CronTrigger(hour=settings.campaign.reminder_deadline_hour, minute=0),
        args=[bot],
        id="daily_reminder",
        replace_existing=True,
    )
    scheduler.add_job(
        missed_job,
        CronTrigger(hour=settings.campaign.missed_deadline_hour, minute=0),
        args=[bot],
        id="missed_notification",
        replace_existing=True,
    )
    scheduler.add_job(heartbeat_job, CronTrigger(minute="*/10"), id="heartbeat", replace_existing=True)
    scheduler.start()

    logger.info("Scheduler started")
    while True:
        await dispatch_admin_errors(bot)
        await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(main())
