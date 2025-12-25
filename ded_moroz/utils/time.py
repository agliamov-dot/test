from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from ded_moroz.config import settings


def now() -> datetime:
    return datetime.now(ZoneInfo(settings.campaign.timezone))


def campaign_start_datetime() -> datetime:
    return datetime.combine(settings.campaign.start_date, time(0, 0), tzinfo=ZoneInfo(settings.campaign.timezone))


def campaign_end_datetime() -> datetime:
    return campaign_start_datetime() + timedelta(days=settings.campaign.days)


def current_campaign_day(current: datetime | None = None, clamp: bool = True) -> int:
    current_dt = current or now()
    start_dt = campaign_start_datetime()
    delta = current_dt - start_dt
    day = delta.days + 1
    if not clamp:
        return day
    return max(1, min(settings.campaign.days, day))


def is_campaign_active(current: datetime | None = None) -> bool:
    current_dt = current or now()
    return campaign_start_datetime() <= current_dt < campaign_end_datetime()


def is_before_start(current: datetime | None = None) -> bool:
    current_dt = current or now()
    return current_dt < campaign_start_datetime()


def reminder_window(current: datetime | None = None) -> bool:
    current_dt = current or now()
    return current_dt.time().hour >= settings.campaign.reminder_deadline_hour


def missed_window(current: datetime | None = None) -> bool:
    current_dt = current or now()
    return current_dt.time().hour >= settings.campaign.missed_deadline_hour


def quiet_hours_window(current: datetime | None = None) -> tuple[datetime, datetime]:
    current_dt = (current or now()).astimezone(ZoneInfo(settings.campaign.timezone))
    start = settings.campaign.quiet_hours_start
    end = settings.campaign.quiet_hours_end
    start_dt = datetime.combine(current_dt.date(), time(start, 0), tzinfo=current_dt.tzinfo)
    end_dt = datetime.combine(current_dt.date(), time(end, 0), tzinfo=current_dt.tzinfo)

    if start == end:
        return start_dt, start_dt
    if end <= start:
        end_dt += timedelta(days=1)
    return start_dt, end_dt


def quiet_hours_end(current: datetime | None = None) -> datetime:
    current_dt = (current or now()).astimezone(ZoneInfo(settings.campaign.timezone))
    start_dt, end_dt = quiet_hours_window(current_dt)
    if current_dt < start_dt:
        return start_dt
    return end_dt


def is_quiet_hours(current: datetime | None = None) -> bool:
    current_dt = (current or now()).astimezone(ZoneInfo(settings.campaign.timezone))
    start_dt, end_dt = quiet_hours_window(current_dt)
    if start_dt == end_dt:
        return False
    return start_dt <= current_dt < end_dt


def day_deadline(day: int, deadline_hour: int | None = None) -> datetime:
    tz = ZoneInfo(settings.campaign.timezone)
    hour = deadline_hour if deadline_hour is not None else settings.campaign.missed_deadline_hour
    base_date = settings.campaign.start_date + timedelta(days=day - 1)
    return datetime.combine(base_date, time(hour, 0), tzinfo=tz)


def current_day_deadline(current: datetime | None = None) -> tuple[int, datetime]:
    current_dt = current or now()
    day = current_campaign_day(current_dt, clamp=True)
    return day, day_deadline(day)


def is_after_deadline(current: datetime | None = None) -> bool:
    current_dt = current or now()
    _, deadline_dt = current_day_deadline(current_dt)
    return current_dt >= deadline_dt


def day_bounds(target_day: int) -> tuple[datetime, datetime]:
    start = campaign_start_datetime() + timedelta(days=target_day - 1)
    end = start + timedelta(days=1)
    return start, end
