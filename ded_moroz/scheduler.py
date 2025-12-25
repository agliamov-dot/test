from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from datetime import time as dt_time

from aiogram import Bot
from apscheduler.events import EVENT_JOB_ERROR, JobExecutionEvent
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from ded_moroz.config import settings
from ded_moroz.services.admin_notifications import dispatch_admin_errors
from ded_moroz.services.logging import log_error
from ded_moroz.services.notifications import send_daily_reminders, send_missed_notifications
from ded_moroz.services.heartbeat import beat
from ded_moroz.db.models import SeverityLevel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def reminder_job(bot: Bot) -> None:
    await send_daily_reminders(bot)


async def missed_job(bot: Bot) -> None:
    await send_missed_notifications(bot)


async def heartbeat_job() -> None:
    await beat("scheduler", interval_seconds=60)


def _parse_time(value: str | None, default_hour: int) -> dt_time:
    if not value:
        return dt_time(hour=default_hour, minute=0)
    try:
        hours, minutes = value.split(":")
        return dt_time(hour=int(hours), minute=int(minutes))
    except ValueError:
        return dt_time(hour=default_hour, minute=0)


def _on_job_error(event: JobExecutionEvent) -> None:
    if not event.exception:
        return
    asyncio.create_task(
        log_error(
            SeverityLevel.ERROR,
            "Scheduler job failed",
            {"job_id": event.job_id, "exception": str(event.exception)},
            service_name="scheduler",
        )
    )


async def main() -> None:
    bot = Bot(token=settings.service.bot_token)
    scheduler = AsyncIOScheduler(timezone=settings.campaign.timezone)

    reminder_time = _parse_time(os.getenv("REMINDER_TIME"), settings.campaign.reminder_deadline_hour)
    missed_time = _parse_time(os.getenv("MISSED_NOTIFY_TIME"), settings.campaign.missed_deadline_hour)

    scheduler.add_job(
        reminder_job,
        CronTrigger(hour=reminder_time.hour, minute=reminder_time.minute),
        args=[bot],
        id="daily_reminder",
        replace_existing=True,
    )
    scheduler.add_job(
        missed_job,
        CronTrigger(hour=missed_time.hour, minute=missed_time.minute),
        args=[bot],
        id="missed_notification",
        replace_existing=True,
    )
    scheduler.add_job(heartbeat_job, CronTrigger(minute="*"), id="heartbeat", replace_existing=True)
    scheduler.add_listener(_on_job_error, EVENT_JOB_ERROR)
    scheduler.start()

    logger.info("Scheduler started")
    while True:
        await dispatch_admin_errors(bot)
        await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(main())
