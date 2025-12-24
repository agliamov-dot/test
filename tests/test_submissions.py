from __future__ import annotations

import pytest

from ded_moroz.services.submissions import SubmissionExistsError, save_submission
from ded_moroz.services.users import get_or_create_user


@pytest.mark.asyncio
async def test_submission_unique(engine) -> None:  # noqa: ARG001
    user = await get_or_create_user(telegram_id=2, username="user", first_name="A", last_name="B")
    await save_submission(
        user,
        day=1,
        poem_text="test",
        decision="ACCEPT",
        ded_moroz_reply="ok",
        scores=None,
        reasons=None,
        safety_flag=False,
    )
    with pytest.raises(SubmissionExistsError):
        await save_submission(
            user,
            day=1,
            poem_text="test",
            decision="ACCEPT",
            ded_moroz_reply="ok",
            scores=None,
            reasons=None,
            safety_flag=False,
        )
