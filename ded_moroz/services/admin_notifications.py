from __future__ import annotations

from aiogram import Bot

from ded_moroz.config import settings
from ded_moroz.services.logging import fetch_pending_admin_errors, mark_admin_error_notified


async def dispatch_admin_errors(bot: Bot) -> int:
    admins = settings.admins.admin_ids
    if not admins:
        return 0
    pending = await fetch_pending_admin_errors()
    if not pending:
        return 0
    sent = 0
    for item in pending:
        error = item.error
        message = f"[ERROR] {error.level}: {error.message}\nContext: {error.context}"
        for admin_id in admins:
            await bot.send_message(admin_id, message)
            sent += 1
        await mark_admin_error_notified(item)
    return sent
