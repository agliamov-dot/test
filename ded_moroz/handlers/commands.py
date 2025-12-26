from __future__ import annotations

import json
import os
import logging
from datetime import date
from typing import Final

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ded_moroz.config import settings
from ded_moroz.db.models import GiftType, SeverityLevel, UserStatus
from ded_moroz.handlers.helpers import format_status, is_admin
from ded_moroz.llm.client import LlmClientError, LlmResponse, OpenRouterClient
from ded_moroz.services import submissions as submissions_service
from ded_moroz.services.gifts import get_gift_for_day, list_gifts, set_gift
from ded_moroz.services.logging import fetch_recent_errors, log_error
from ded_moroz.services.users import get_or_create_user, get_user_by_telegram, update_status
from ded_moroz.utils.time import (
    current_campaign_day,
    current_day_deadline,
    is_after_deadline,
    is_before_start,
    is_campaign_active,
    is_quiet_hours,
    now,
    quiet_hours_end,
)

POEM_MIN_LENGTH: Final[int] = 10
POEM_MAX_LENGTH: Final[int] = 1500

router = Router()
llm_client = OpenRouterClient()
logger = logging.getLogger(__name__)


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


def _main_keyboard(user_status: UserStatus) -> InlineKeyboardMarkup:
    inline_keyboard = [
        [InlineKeyboardButton(text="Сдать стих за сегодня", callback_data="gift:submit")],
        [InlineKeyboardButton(text="Статус", callback_data="status:show")],
    ]
    if user_status == UserStatus.PAUSED:
        inline_keyboard.append([InlineKeyboardButton(text="Продолжить", callback_data="user:resume")])
    else:
        inline_keyboard.append([InlineKeyboardButton(text="Пауза", callback_data="user:pause")])
    inline_keyboard.append([InlineKeyboardButton(text="Остановить", callback_data="user:stop_confirm")])
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def _stop_confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Да, остановить", callback_data="user:stop"),
                InlineKeyboardButton(text="Отмена", callback_data="user:stop_cancel"),
            ]
        ]
    )


async def _respond(target: Message | CallbackQuery, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
    if isinstance(target, CallbackQuery):
        await target.answer()
        message = target.message
    else:
        message = target
    if message:
        await message.answer(text, reply_markup=reply_markup)


async def _ensure_admin(message: Message) -> bool:
    telegram_id = message.from_user.id
    if is_admin(telegram_id):
        logger.info("Admin access granted", extra={"telegram_id": telegram_id, "command": message.text})
        return True
    await log_error(
        SeverityLevel.WARNING,
        "Admin access denied",
        {"telegram_id": telegram_id, "command": message.text},
        service_name="bot",
    )
    logger.warning("Admin access denied", extra={"telegram_id": telegram_id, "command": message.text})
    await message.answer("У тебя нет прав администратора.")
    return False


def _format_error_entry(error: object) -> str:
    created_at = getattr(error, "created_at", None)
    created_part = f" [{created_at.strftime('%d.%m %H:%M')}]" if created_at else ""
    context = getattr(error, "context", None)
    context_part = f" — контекст: {context}" if context else ""
    return f"#{getattr(error, 'id', '?')} [{getattr(error, 'level', '?')}] {getattr(error, 'message', '')}{created_part}{context_part}"


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name,
    )
    if user.status == UserStatus.STOPPED:
        await update_status(user.id, UserStatus.ACTIVE)
        user.status = UserStatus.ACTIVE
    keyboard = _main_keyboard(user.status)
    await message.answer(
        "Хо-хо-хо! Ты в игре. Каждый день жду твой стих, чтобы открыть подарок. "
        "Пиши текстом, а я проверю через волшебство ИИ.",
        reply_markup=keyboard,
    )


@router.message(Command("pause"))
async def cmd_pause(message: Message) -> None:
    user = await get_user_by_telegram(message.from_user.id)
    if not user:
        await message.answer("Сначала нажми /start, чтобы присоединиться.")
        return
    await update_status(user.id, UserStatus.PAUSED)
    await message.answer("Понял, делаю паузу. Возвращайся, когда будешь готов.", reply_markup=_main_keyboard(UserStatus.PAUSED))


@router.message(Command("resume"))
async def cmd_resume(message: Message) -> None:
    user = await get_user_by_telegram(message.from_user.id)
    if not user:
        await message.answer("Сначала нажми /start, чтобы присоединиться.")
        return
    await update_status(user.id, UserStatus.ACTIVE)
    await message.answer("Продолжаем! Снова жду твои стихи.", reply_markup=_main_keyboard(UserStatus.ACTIVE))


@router.message(Command("stop"))
async def cmd_stop(message: Message) -> None:
    user = await get_user_by_telegram(message.from_user.id)
    if not user:
        await message.answer("Ты ещё не в игре. Нажми /start.")
        return
    await message.answer("Точно остановить участие? Ты перестанешь получать уведомления.", reply_markup=_stop_confirmation_keyboard())


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    user = await get_user_by_telegram(message.from_user.id)
    if not user:
        await message.answer("Я тебя ещё не видел. /start, чтобы начать.")
        return
    await message.answer(format_status(user), reply_markup=_main_keyboard(user.status))


@router.message(Command("admin_stats"))
async def cmd_admin_stats(message: Message) -> None:
    if not await _ensure_admin(message):
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
    if not await _ensure_admin(message):
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
    if not await _ensure_admin(message):
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
    await log_error(
        SeverityLevel.INFO,
        "Gift updated",
        {"day": day, "gift_type": gift_type.value, "admin_id": message.from_user.id},
        service_name="gifts",
    )
    await message.answer(f"Подарок на день {gift.day} обновлён.")


@router.message(Command("get_gift"))
async def cmd_get_gift(message: Message, command: CommandObject) -> None:
    if not await _ensure_admin(message):
        return
    if not command.args:
        await message.answer("Используй: /get_gift <day>")
        return
    day = int(command.args.strip())
    gift = await get_gift_for_day(day)
    if not gift:
        await log_error(
            SeverityLevel.WARNING,
            "Gift not found",
            {"day": day, "admin_id": message.from_user.id},
            service_name="gifts",
        )
        await message.answer("Подарок не найден")
        return
    payload_line = f" payload={gift.payload}" if gift.payload else ""
    await message.answer(
        f"День {gift.day}: тип={gift.gift_type.value} текст={gift.gift_text or ''} url={gift.gift_url or ''}{payload_line}"
    )


@router.message(Command("admin_gifts"))
async def cmd_admin_gifts(message: Message) -> None:
    if not await _ensure_admin(message):
        return
    gifts = await list_gifts()
    gifts_by_day = {gift.day: gift for gift in gifts}
    missing_days: list[int] = []
    lines = []
    for day in range(1, settings.campaign.days + 1):
        gift = gifts_by_day.get(day)
        if gift:
            lines.append(f"День {day}: {_format_gift_line(gift)}")
        else:
            lines.append(f"День {day}: подарок не настроен")
            missing_days.append(day)
    response_parts = ["Статус подарков:", "\n".join(lines)]
    if missing_days:
        errors = await fetch_recent_errors(limit=10, service_name="gifts", message_query="Gift")
        if not errors:
            errors = await fetch_recent_errors(limit=10, message_query="gift")
        if errors:
            response_parts.append("Последние записи журнала по подаркам:")
            response_parts.extend([_format_error_entry(error) for error in errors])
        else:
            response_parts.append("Логов по подаркам пока нет — добавь подарки и повтори команду.")
    await message.answer("\n".join(response_parts))


@router.message(Command("admin_errors"))
async def cmd_admin_errors(message: Message) -> None:
    if not await _ensure_admin(message):
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
    if not await _ensure_admin(message):
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
    if not await _ensure_admin(message):
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


@router.message(Command("campaign_start"))  # noqa: D401
async def cmd_campaign_start(message: Message, command: CommandObject) -> None:
    if not await _ensure_admin(message):
        return
    if not command.args:
        current_day = current_campaign_day()
        await message.answer(
            f"Текущая дата старта кампании: {settings.campaign.start_date.isoformat()} "
            f"(сейчас день {current_day} из {settings.campaign.days}).\n"
            "Чтобы поменять дату, используй: /campaign_start YYYY-MM-DD"
        )
        return
    try:
        new_start = date.fromisoformat(command.args.strip())
    except ValueError:
        await message.answer("Формат даты: YYYY-MM-DD")
        return
    settings.campaign.start_date = new_start
    os.environ["CAMPAIGN_START_DATE"] = new_start.isoformat()
    await log_error(
        SeverityLevel.INFO,
        "Campaign start date updated",
        {"start_date": new_start.isoformat(), "admin_id": message.from_user.id},
        service_name="campaign",
    )
    await message.answer(
        f"Старт кампании обновлён на {new_start.isoformat()}. "
        f"Текущий день: {current_campaign_day()} из {settings.campaign.days}."
    )


@router.message(Command("campaign_reset_dates"))
async def cmd_campaign_reset_dates(message: Message) -> None:
    if not await _ensure_admin(message):
        return
    today = now().date()
    settings.campaign.start_date = today
    os.environ["CAMPAIGN_START_DATE"] = today.isoformat()
    await log_error(
        SeverityLevel.INFO,
        "Campaign dates reset for testing",
        {"start_date": today.isoformat(), "admin_id": message.from_user.id},
        service_name="campaign",
    )
    await message.answer(
        "Даты кампании сброшены для тестирования. "
        f"Старт теперь {today.isoformat()}, расчёт дня начинается заново."
    )


@router.callback_query(F.data == "status:show")
async def cq_status(callback: CallbackQuery) -> None:
    user = await get_user_by_telegram(callback.from_user.id)
    if not user:
        await _respond(callback, "Я тебя ещё не видел. Нажми /start, чтобы начать.")
        return
    await _respond(callback, format_status(user), reply_markup=_main_keyboard(user.status))


@router.message(Command("gift"))
async def cmd_gift(message: Message) -> None:
    await _handle_gift_request(message)


@router.callback_query(F.data == "gift:submit")
async def cq_gift(callback: CallbackQuery) -> None:
    await _handle_gift_request(callback)


async def _handle_gift_request(target: Message | CallbackQuery) -> None:
    user = await get_user_by_telegram(target.from_user.id)
    if not user:
        await _respond(target, "Сначала нажми /start, чтобы присоединиться.")
        return
    if user.status == UserStatus.STOPPED:
        await _respond(target, "Ты остановил участие. Вернись командой /start.")
        return
    if user.status == UserStatus.PAUSED:
        await _respond(target, "Ты на паузе. /resume — и снова в бой.", reply_markup=_main_keyboard(user.status))
        return
    if is_before_start():
        await _respond(target, "Кампания ещё не началась. Потерпи чуть-чуть!")
        return
    if not is_campaign_active():
        await _respond(target, "Кампания уже завершилась. Спасибо за участие!")
        return
    if is_quiet_hours():
        quiet_end = quiet_hours_end()
        await _respond(
            target,
            f"Сейчас тихие часы. Жду твой стих после {quiet_end.strftime('%d.%m %H:%M %Z')}.",
        )
        return

    day, deadline_dt = current_day_deadline()
    if is_after_deadline():
        await _respond(
            target,
            f"Дедлайн на сегодня ({deadline_dt.strftime('%H:%M %Z')}) уже прошёл. Жду тебя завтра!",
        )
        return

    if await submissions_service.has_submission(user.id, day):
        gift = await get_gift_for_day(day)
        gift_line = _format_gift_line(gift)
        await _respond(target, f"На сегодня всё! {gift_line}")
        return

    attempts = await submissions_service.count_attempts(user.id, day)
    if attempts >= settings.campaign.max_attempts_per_day:
        await _respond(target, "Лимит попыток на сегодня исчерпан. Приходи завтра.")
        return
    attempts_left = settings.campaign.max_attempts_per_day - attempts
    attempts_hint = (
        f" Осталось попыток: {attempts_left}." if attempts_left < settings.campaign.max_attempts_per_day else ""
    )
    await _respond(
        target,
        f"День {day}. Присылай стих текстом, чтобы открыть подарок. Дедлайн сегодня: {deadline_dt.strftime('%H:%M %Z')}."
        f"{attempts_hint}",
    )


@router.callback_query(F.data == "user:pause")
async def cq_pause(callback: CallbackQuery) -> None:
    user = await get_user_by_telegram(callback.from_user.id)
    if not user:
        await _respond(callback, "Сначала нажми /start, чтобы присоединиться.")
        return
    await update_status(user.id, UserStatus.PAUSED)
    await _respond(callback, "Понял, делаю паузу. Возвращайся, когда будешь готов.", reply_markup=_main_keyboard(UserStatus.PAUSED))


@router.callback_query(F.data == "user:resume")
async def cq_resume(callback: CallbackQuery) -> None:
    user = await get_user_by_telegram(callback.from_user.id)
    if not user:
        await _respond(callback, "Сначала нажми /start, чтобы присоединиться.")
        return
    await update_status(user.id, UserStatus.ACTIVE)
    await _respond(callback, "Продолжаем! Снова жду твои стихи.", reply_markup=_main_keyboard(UserStatus.ACTIVE))


@router.callback_query(F.data == "user:stop_confirm")
async def cq_stop_confirm(callback: CallbackQuery) -> None:
    user = await get_user_by_telegram(callback.from_user.id)
    if not user:
        await _respond(callback, "Ты ещё не в игре. Нажми /start.")
        return
    await _respond(callback, "Точно остановить участие? Ты перестанешь получать уведомления.", reply_markup=_stop_confirmation_keyboard())


@router.callback_query(F.data == "user:stop")
async def cq_stop(callback: CallbackQuery) -> None:
    user = await get_user_by_telegram(callback.from_user.id)
    if not user:
        await _respond(callback, "Ты ещё не в игре. Нажми /start.")
        return
    await update_status(user.id, UserStatus.STOPPED)
    await _respond(callback, "Жаль расставаться. Если передумаешь — /start.")


@router.callback_query(F.data == "user:stop_cancel")
async def cq_stop_cancel(callback: CallbackQuery) -> None:
    user = await get_user_by_telegram(callback.from_user.id)
    status = user.status if user else UserStatus.ACTIVE
    await _respond(callback, "Отмена. Я с тобой!", reply_markup=_main_keyboard(status))


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
    if is_quiet_hours():
        quiet_end = quiet_hours_end()
        await message.answer(f"Сейчас тихие часы. Жду стих после {quiet_end.strftime('%d.%m %H:%M %Z')}.")
        return

    day, deadline_dt = current_day_deadline()
    if is_after_deadline():
        await message.answer(f"Дедлайн на сегодня ({deadline_dt.strftime('%H:%M %Z')}) уже прошёл. Жду тебя завтра!")
        return

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
    if not isinstance(poem_text, str):
        await message.answer("Я жду текстовое сообщение со стихом. Голосовые и вложения не подойдут.")
        return
    poem_text = poem_text.strip()
    if len(poem_text) < POEM_MIN_LENGTH:
        attempts_left = settings.campaign.max_attempts_per_day - attempts
        suffix = f" Попыток осталось: {attempts_left}." if attempts_left else ""
        await message.answer(
            f"Стих слишком короткий — добавь деталей и эмоций (минимум {POEM_MIN_LENGTH} символов).{suffix}"
        )
        return
    if len(poem_text) > POEM_MAX_LENGTH:
        attempts_left = settings.campaign.max_attempts_per_day - attempts
        suffix = f" Попыток осталось: {attempts_left}." if attempts_left else ""
        await message.answer(
            f"Стих слишком длинный — уложись в {POEM_MAX_LENGTH} символов и пришли снова.{suffix}"
        )
        return

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
    except LlmClientError as exc:
        await log_error(
            SeverityLevel.ERROR,
            "LLM evaluation failed",
            {"error": str(exc), "user_id": user.id, "day": day},
            service_name="bot",
        )
        await message.answer("Моё волшебство сегодня не отвечает. Попробуй позже — попытка не сгорела.")
    except Exception as exc:  # noqa: BLE001
        await log_error(SeverityLevel.ERROR, "Processing poem failed", {"error": str(exc)}, service_name="bot")
        await message.answer("Моё волшебство дало сбой. Попробуй позже.")
