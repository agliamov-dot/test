from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from ded_moroz.config import settings
from ded_moroz.handlers import commands
from ded_moroz.services.admin_notifications import dispatch_admin_errors

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.include_router(commands.router)
    return dispatcher


async def main() -> None:
    bot = Bot(token=settings.service.bot_token)
    dp = create_dispatcher()

    async def error_notifier() -> None:
        while True:
            await dispatch_admin_errors(bot)
            await asyncio.sleep(60)

    notifier_task = asyncio.create_task(error_notifier())
    try:
        await dp.start_polling(bot)
    finally:
        notifier_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await notifier_task


if __name__ == "__main__":
    import contextlib

    asyncio.run(main())
