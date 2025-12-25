from __future__ import annotations

from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ded_moroz.db.models import (
    NotificationLog,
    NotificationType,
    PoemAttempt,
    SafetyStatus,
    Submission,
    User,
    UserStatus,
)
from ded_moroz.db.session import session_scope


class SubmissionExistsError(Exception):
    pass


async def has_submission(user_id: int, day: int) -> bool:
    async with session_scope() as session:
        result = await session.execute(select(Submission.id).where(Submission.user_id == user_id, Submission.day == day))
        return result.scalar_one_or_none() is not None


async def get_submissions_for_users(user_ids: Sequence[int], day: int) -> set[int]:
    if not user_ids:
        return set()
    async with session_scope() as session:
        result = await session.execute(
            select(Submission.user_id).where(Submission.user_id.in_(user_ids), Submission.day == day)
        )
        return set(result.scalars())


async def count_attempts(user_id: int, day: int) -> int:
    async with session_scope() as session:
        result = await session.execute(select(PoemAttempt.id).where(PoemAttempt.user_id == user_id, PoemAttempt.day == day))
        return len(result.scalars().all())


async def record_attempt(
    user: User,
    day: int,
    poem_text: str,
    decision: str,
    ded_moroz_reply: str,
    scores: dict[str, Any] | None,
    reasons: dict[str, Any] | None,
    safety_flag: bool,
    safety_status: SafetyStatus,
) -> PoemAttempt:
    async with session_scope() as session:
        attempt = PoemAttempt(
            user_id=user.id,
            day=day,
            poem_text=poem_text,
            decision=decision,
            ded_moroz_reply=ded_moroz_reply,
            scores=scores,
            reasons=reasons,
            safety_flag=safety_flag,
            safety_status=safety_status,
        )
        session.add(attempt)
        return attempt


async def save_submission(
    user: User,
    day: int,
    poem_text: str,
    decision: str,
    ded_moroz_reply: str,
    scores: dict[str, Any] | None,
    reasons: dict[str, Any] | None,
    safety_flag: bool,
    safety_status: SafetyStatus,
) -> Submission:
    async with session_scope() as session:
        submission = Submission(
            user_id=user.id,
            day=day,
            poem_text=poem_text,
            decision=decision,
            ded_moroz_reply=ded_moroz_reply,
            scores=scores,
            reasons=reasons,
            safety_flag=safety_flag,
            safety_status=safety_status,
        )
        session.add(submission)
        try:
            await session.flush()
        except IntegrityError as exc:
            raise SubmissionExistsError from exc
        return submission


async def create_notification_log(user_id: int, day: int, notification_type: NotificationType) -> bool:
    async with session_scope() as session:
        record = NotificationLog(user_id=user_id, day=day, notification_type=notification_type)
        session.add(record)
        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()
            return False
        return True


async def create_notification_logs_batch(user_ids: Sequence[int], day: int, notification_type: NotificationType) -> set[int]:
    if not user_ids:
        return set()

    async with session_scope() as session:
        existing_result = await session.execute(
            select(NotificationLog.user_id)
            .where(NotificationLog.user_id.in_(user_ids))
            .where(NotificationLog.day == day)
            .where(NotificationLog.notification_type == notification_type)
        )
        existing_ids = set(existing_result.scalars())
        pending_ids = [user_id for user_id in user_ids if user_id not in existing_ids]
        if not pending_ids:
            return set()

        session.add_all(
            [NotificationLog(user_id=user_id, day=day, notification_type=notification_type) for user_id in pending_ids]
        )
        return set(pending_ids)
