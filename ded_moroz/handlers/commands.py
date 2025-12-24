from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

import json

from ded_moroz.config import settings
from ded_moroz.db.models import GiftType, SeverityLevel, UserStatus
from ded_moroz.handlers.helpers import format_status, is_admin
from ded_moroz.llm.client import LlmResponse, OpenRouterClient
from ded_moroz.services import submissions as submissions_service
from ded_moroz.services.gifts import get_gift_for_day, set_gift
from ded_moroz.services.logging import log_error
from ded_moroz.services.users import get_or_create_user, get_user_by_telegram, update_status
from ded_moroz.utils.time import current_campaign_day, is_before_start, is_campaign_active

router = Router()
llm_client = OpenRouterClient()


def _format_gift_line(gift: object) -> str:
    if not gift:
        return "Подарок пока не настроен."
    if getattr(gift, "gift_type", None) == GiftType.PAYLOAD and getattr(gift, "payload", None) is not None:
        return json.dumps(gift.payload, ensure_ascii=False)
    if getattr(gift, "gift_type", None) == GiftType.URL and getattr(gift, "gift_url", None):
        return gift.gift_url
    if getattr(gift, "gift_text", None):
        return gift.gift_text
    if getattr(gift, "gift_url", None):
        return gift.gift_url
    return "Подарок пока не настроен."


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name,
    )
    await message.answer(
        "Хо-хо-хо! Ты в игре. Каждый день жду твой стих, чтобы открыть подарок. "
        "Пиши текстом, а я проверю через волшебство ИИ."
    )


@router.message(Command("pause"))
async def cmd_pause(message: Message) -> None:
    user = await get_user_by_telegram(message.from_user.id)
    if not user:
        await message.answer("Сначала нажми /start, чтобы присоединиться.")
        return
    await update_status(user.id, UserStatus.PAUSED)
    await message.answer("Понял, делаю паузу. Возвращайся, когда будешь готов.")


@router.message(Command("resume"))
async def cmd_resume(message: Message) -> None:
    user = await get_user_by_telegram(message.from_user.id)
    if not user:
        await message.answer("Сначала нажми /start, чтобы присоединиться.")
        return
    await update_status(user.id, UserStatus.ACTIVE)
    await message.answer("Продолжаем! Снова жду твои стихи.")


@router.message(Command("stop"))
async def cmd_stop(message: Message) -> None:
    user = await get_user_by_telegram(message.from_user.id)
    if not user:
        await message.answer("Ты ещё не в игре. Нажми /start.")
        return
    await update_status(user.id, UserStatus.STOPPED)
    await message.answer("Жаль расставаться. Если передумаешь — /start." )


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    user = await get_user_by_telegram(message.from_user.id)
    if not user:
        await message.answer("Я тебя ещё не видел. /start, чтобы начать.")
        return
    await message.answer(format_status(user))


@router.message(Command("admin_stats"))
async def cmd_admin_stats(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    from sqlalchemy import func, select

    from ded_moroz.db.models import NotificationLog, Submission, User
    from ded_moroz.db.session import session_scope

    async with session_scope() as session:
        users_count = (await session.execute(select(func.count(User.id)))).scalar_one()
        submissions_count = (await session.execute(select(func.count(Submission.id)))).scalar_one()
        notifications_count = (await session.execute(select(func.count(NotificationLog.id)))).scalar_one()

    await message.answer(
        f"Пользователей: {users_count}\n"
        f"Сабмишены: {submissions_count}\n"
        f"Уведомления: {notifications_count}"
    )


@router.message(Command("admin_user"))
async def cmd_admin_user(message: Message, command: CommandObject) -> None:
    if not is_admin(message.from_user.id):
        return
    if not command.args:
        await message.answer("Используй: /admin_user <telegram_id>")
        return
    try:
        telegram_id = int(command.args.strip())
    except ValueError:
        await message.answer("ID должен быть числом")
        return
    user = await get_user_by_telegram(telegram_id)
    if not user:
        await message.answer("Пользователь не найден")
        return
    await message.answer(format_status(user))


@router.message(Command("set_gift"))
async def cmd_set_gift(message: Message, command: CommandObject) -> None:
    if not is_admin(message.from_user.id):
        return
    if not command.args:
        await message.answer("Используй: /set_gift <day> <текст> [url]")
        return
    parts = command.args.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer("Нужно указать день и текст")
        return
    day = int(parts[0])
    raw_type_or_text = parts[1]
    gift_type = GiftType.TEXT
    payload_data: dict | None = None
    gift_text: str | None = None
    gift_url: str | None = None

    if raw_type_or_text in {t.value for t in GiftType}:
        gift_type = GiftType(raw_type_or_text)
        if len(parts) < 3:
            await message.answer("Нужно указать содержимое подарка для выбранного типа.")
            return
        content = parts[2]
    else:
        content = raw_type_or_text
        gift_url = parts[2] if len(parts) == 3 else None

    if gift_type == GiftType.TEXT:
        gift_text = content
    elif gift_type == GiftType.URL:
        gift_url = content
    elif gift_type == GiftType.PAYLOAD:
        try:
            payload_data = json.loads(content)
        except json.JSONDecodeError:
            await message.answer("Payload должен быть валидным JSON.")
            return

    gift = await set_gift(day, gift_type, gift_text, gift_url, payload_data)
    await message.answer(f"Подарок на день {gift.day} обновлён.")


@router.message(Command("get_gift"))
async def cmd_get_gift(message: Message, command: CommandObject) -> None:
    if not is_admin(message.from_user.id):
        return
    if not command.args:
        await message.answer("Используй: /get_gift <day>")
        return
    day = int(command.args.strip())
    gift = await get_gift_for_day(day)
    if not gift:
        await message.answer("Подарок не найден")
        return
    payload_line = f" payload={gift.payload}" if gift.payload else ""
    await message.answer(
        f"День {gift.day}: тип={gift.gift_type.value} текст={gift.gift_text or ''} url={gift.gift_url or ''}{payload_line}"
    )


@router.message(Command("admin_errors"))
async def cmd_admin_errors(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    from sqlalchemy import select

    from ded_moroz.db.models import ErrorLog
    from ded_moroz.db.session import session_scope

    async with session_scope() as session:
        result = await session.execute(select(ErrorLog).order_by(ErrorLog.id.desc()).limit(10))
        errors = result.scalars().all()
    if not errors:
        await message.answer("Ошибок нет")
        return
    lines = [f"#{err.id} {err.level} {err.message}" for err in errors]
    await message.answer("\n".join(lines))


@router.message(Command("admin_error"))
async def cmd_admin_error(message: Message, command: CommandObject) -> None:
    if not is_admin(message.from_user.id):
        return
    if not command.args:
        await message.answer("Используй: /admin_error <id>")
        return
    err_id = int(command.args)
    from ded_moroz.db.session import session_scope
    from ded_moroz.db.models import ErrorLog

    async with session_scope() as session:
        error = await session.get(ErrorLog, err_id)
    if not error:
        await message.answer("Не найдено")
        return
    await message.answer(f"{error.level}\n{error.message}\nКонтекст: {error.context}")


@router.message(Command("admin_health"))
async def cmd_admin_health(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    from sqlalchemy import select

    from ded_moroz.db.models import ServiceHeartbeat
    from ded_moroz.db.session import session_scope

    async with session_scope() as session:
        result = await session.execute(select(ServiceHeartbeat).order_by(ServiceHeartbeat.service_name))
        heartbeats = result.scalars().all()
    if not heartbeats:
        await message.answer("Пульс не найден")
        return
    lines = [f"{hb.service_name}: {hb.last_beat_at} (freq: {hb.beat_interval_seconds}s)" for hb in heartbeats]
    await message.answer("\n".join(lines))


@router.message(F.text)
async def process_poem(message: Message) -> None:
    user = await get_user_by_telegram(message.from_user.id)
    if not user:
        await message.answer("Сначала нажми /start, чтобы начать игру.")
        return
    if user.status == UserStatus.STOPPED:
        await message.answer("Ты остановил уведомления. Вернись командой /start.")
        return
    if user.status == UserStatus.PAUSED:
        await message.answer("Ты на паузе. /resume — и снова в бой.")
        return
    if is_before_start():
        await message.answer("Кампания ещё не началась. Потерпи чуть-чуть!")
        return
    if not is_campaign_active():
        await message.answer("Кампания уже завершилась. Спасибо за участие!")
        return

    day = current_campaign_day()
    if await submissions_service.has_submission(user.id, day):
        gift = await get_gift_for_day(day)
        gift_line = _format_gift_line(gift)
        await message.answer(f"На сегодня всё! {gift_line}")
        return

    attempts = await submissions_service.count_attempts(user.id, day)
    if attempts >= settings.campaign.max_attempts_per_day:
        await message.answer("Лимит попыток на сегодня исчерпан. Приходи завтра.")
        return

    poem_text = message.text
    try:
        llm_result: LlmResponse = await llm_client.evaluate_poem(poem_text, day, user.id)
        await submissions_service.record_attempt(
            user,
            day,
            poem_text,
            llm_result.decision,
            llm_result.ded_moroz_reply,
            llm_result.scores,
            llm_result.reasons,
            llm_result.safety_flag,
            llm_result.safety_status,
        )
        if llm_result.decision == "ACCEPT":
            try:
                await submissions_service.save_submission(
                    user,
                    day,
                    poem_text,
                    llm_result.decision,
                    llm_result.ded_moroz_reply,
                    llm_result.scores,
                    llm_result.reasons,
                    llm_result.safety_flag,
                    llm_result.safety_status,
                )
            except submissions_service.SubmissionExistsError:
                pass
            gift = await get_gift_for_day(day)
            gift_line = _format_gift_line(gift)
            await message.answer(f"{llm_result.ded_moroz_reply}\nТвой подарок: {gift_line}")
        else:
            attempts_left = settings.campaign.max_attempts_per_day - attempts - 1
            suffix = f" Осталось попыток: {attempts_left}." if attempts_left > 0 else ""
            await message.answer(f"{llm_result.ded_moroz_reply}{suffix}")
    except Exception as exc:  # noqa: BLE001
        await log_error(SeverityLevel.ERROR, "Processing poem failed", {"error": str(exc)}, service_name="bot")
        await message.answer("Моё волшебство дало сбой. Попробуй позже.")
