from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from ded_moroz.config import settings


def now() -> datetime:
    return datetime.now(ZoneInfo(settings.campaign.timezone))


def current_campaign_day(current: datetime | None = None) -> int:
    current_dt = current or now()
    start_date = settings.campaign.start_date
    delta = current_dt.date() - start_date
    return delta.days + 1


def is_campaign_active(current: datetime | None = None) -> bool:
    day = current_campaign_day(current)
    return 1 <= day <= settings.campaign.days


def is_before_start(current: datetime | None = None) -> bool:
    current_dt = current or now()
    return current_dt.date() < settings.campaign.start_date


def reminder_window(current: datetime | None = None) -> bool:
    current_dt = current or now()
    return current_dt.time().hour >= settings.campaign.reminder_deadline_hour


def missed_window(current: datetime | None = None) -> bool:
    current_dt = current or now()
    return current_dt.time().hour >= settings.campaign.missed_deadline_hour


def is_quiet_hours(current: datetime | None = None) -> bool:
    current_dt = current or now()
    start = settings.campaign.quiet_hours_start
    end = settings.campaign.quiet_hours_end
    hour = current_dt.time().hour

    if start == end:
        return False
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def day_bounds(target_day: int) -> tuple[datetime, datetime]:
    tz = ZoneInfo(settings.campaign.timezone)
    start = datetime.combine(settings.campaign.start_date + timedelta(days=target_day - 1), time(0, 0), tzinfo=tz)
    end = start + timedelta(days=1)
    return start, end
