from __future__ import annotations

import pytest

from ded_moroz.db.models import NotificationType, User, UserStatus
from ded_moroz.services.submissions import create_notification_log
from ded_moroz.services.users import get_or_create_user


@pytest.mark.asyncio
async def test_notification_log_idempotent(engine) -> None:  # noqa: ARG001
    user = await get_or_create_user(telegram_id=1, username=None, first_name=None, last_name=None)
    created_first = await create_notification_log(user.id, day=1, notification_type=NotificationType.REMINDER)
    created_second = await create_notification_log(user.id, day=1, notification_type=NotificationType.REMINDER)
    assert created_first is True
    assert created_second is False
