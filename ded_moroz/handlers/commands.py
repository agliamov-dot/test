from __future__ import annotations

import json
import os
import logging
from datetime import date
from typing import Final

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
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
    day_deadline,
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


class GiftParseError(ValueError):
    pass


def _parse_set_gift_args(args: str) -> tuple[int, GiftType, str | None, str | None, dict | None]:
    if not args:
        raise GiftParseError("Нужно указать день и содержимое подарка.")

    day_part, *rest = args.split(maxsplit=1)
    try:
        day = int(day_part)
    except ValueError as exc:  # noqa: B904
        raise GiftParseError("День должен быть числом.") from exc

    if not rest:
        raise GiftParseError("Нужно указать текст или тип подарка.")

    remainder = rest[0].strip()
    if not remainder:
        raise GiftParseError("Нужно указать текст или тип подарка.")

    head, *tail = remainder.split(maxsplit=1)
    content = tail[0] if tail else ""
    if head in {t.value for t in GiftType}:
        gift_type = GiftType(head)
    else:
        # Явного типа нет — считаем текстом и берём всю строку целиком
        gift_type = GiftType.TEXT
        content = remainder

    gift_text: str | None = None
    gift_url: str | None = None
    payload_data: dict | None = None

    if gift_type == GiftType.TEXT:
        if not content:
            raise GiftParseError("Нужно указать текст подарка.")
        gift_text = content
    elif gift_type == GiftType.URL:
        if not content:
            raise GiftParseError("Нужно указать ссылку.")
        gift_url = content
    elif gift_type == GiftType.PAYLOAD:
        if not content:
            raise GiftParseError("Payload должен быть валидным JSON.")
        try:
            payload_data = json.loads(content)
        except json.JSONDecodeError as exc:  # noqa: B904
            raise GiftParseError("Payload должен быть валидным JSON.") from exc
    elif gift_type in {GiftType.PHOTO, GiftType.VIDEO, GiftType.AUDIO}:
        if not content:
            raise GiftParseError("Нужно указать ссылку или file_id на медиа.")
        if " " in content:
            gift_url, gift_text = content.split(maxsplit=1)
        else:
            gift_url = content
    else:  # pragma: no cover - запасной случай
        raise GiftParseError("Неподдерживаемый тип подарка.")

    return day, gift_type, gift_text, gift_url, payload_data


def _parse_media_caption(caption: str | None) -> tuple[int | None, str | None]:
    """
    Ожидаем: "<day> [подпись]". Если день не число — вернём (None, caption).
    """
    if not caption:
        return None, None
    parts = caption.strip().split(maxsplit=1)
    try:
        day = int(parts[0])
    except ValueError:
        return None, caption
    text = parts[1] if len(parts) > 1 else None
    return day, text


def _set_welcome_image(value: str, admin_id: int, source: str) -> None:
    settings.service.welcome_image_url = value
    os.environ["WELCOME_IMAGE_URL"] = value
    logger.info("Welcome image updated", extra={"admin_id": admin_id, "source": source})


class GiftSetupStates(StatesGroup):
    waiting_text = State()
    waiting_media = State()


class WelcomeSetupStates(StatesGroup):
    waiting_media = State()


def _format_gift_line(gift: object) -> str:
    if not gift:
        return "Подарок пока не настроен."
    if getattr(gift, "gift_type", None) == GiftType.PAYLOAD and getattr(gift, "payload", None) is not None:
        return json.dumps(gift.payload, ensure_ascii=False)
    text_part = getattr(gift, "gift_text", None)
    url_part = getattr(gift, "gift_url", None)
    parts: list[str] = []
    if text_part:
        parts.append(text_part)
    if url_part and getattr(gift, "gift_type", None) in {GiftType.URL, GiftType.PHOTO, GiftType.VIDEO, GiftType.AUDIO}:
        parts.append(url_part)
    if url_part and not parts:
        parts.append(url_part)
    if parts:
        return "\n".join(parts)
    return "Подарок пока не настроен."


def _main_keyboard(user_status: UserStatus) -> InlineKeyboardMarkup:
    # Оставляем только основную кнопку «Сдать стих», остальные обработчики остаются для обратной совместимости.
    inline_keyboard = [[InlineKeyboardButton(text="Сдать стих за сегодня", callback_data="gift:submit")]]
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


async def _save_media_gift(message: Message, gift_type: GiftType) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("Пришли стих текстом — медиа принимает только админ.")
        return

    day, caption = _parse_media_caption(message.caption)
    if day is None:
        await message.answer("Укажи день в подписи: \"<день> [текст подарка]\".")
        return

    if gift_type == GiftType.PHOTO and message.photo:
        file_id = message.photo[-1].file_id
    elif gift_type == GiftType.VIDEO and message.video:
        file_id = message.video.file_id
    elif gift_type == GiftType.AUDIO and message.audio:
        file_id = message.audio.file_id
    else:
        await message.answer("Не удалось прочитать медиа. Попробуй ещё раз.")
        return

    gift = await set_gift(day, gift_type, caption, file_id, None)
    await log_error(
        SeverityLevel.INFO,
        "Gift updated",
        {"day": day, "gift_type": gift_type.value, "admin_id": message.from_user.id, "via": "media_upload"},
        service_name="gifts",
    )
    await message.answer(f"Подарок на день {gift.day} сохранён (тип {gift_type.value}).")


def _extract_media_from_message(message: Message) -> tuple[GiftType | None, str | None]:
    if message.photo:
        return GiftType.PHOTO, message.photo[-1].file_id
    if message.video:
        return GiftType.VIDEO, message.video.file_id
    if message.audio:
        return GiftType.AUDIO, message.audio.file_id
    if message.document and message.document.mime_type and message.document.mime_type.startswith("image/"):
        return GiftType.PHOTO, message.document.file_id
    return None, None


def _get_bot_and_chat(target: Message | CallbackQuery):
    if isinstance(target, CallbackQuery):
        bot = target.bot
        chat_id = target.message.chat.id if target.message else target.from_user.id
    else:
        bot = target.bot
        chat_id = target.chat.id
    return bot, chat_id


def _next_prompt_line(current_day: int) -> str:
    if current_day >= settings.campaign.days:
        return "🎁 Это был финальный подарок кампании. Спасибо, что был(а) в игре!"
    next_deadline_dt = day_deadline(current_day + 1)
    deadline_str = next_deadline_dt.strftime("%d.%m %H:%M %Z")
    return f"🎅 Жду тебя завтра за следующим подарком. Дедлайн завтра: {deadline_str}."


def _gift_caption(gift, llm_reply: str | None) -> str:
    gift_type = getattr(gift, "gift_type", GiftType.TEXT)
    if gift_type in {GiftType.PHOTO, GiftType.VIDEO, GiftType.AUDIO}:
        gift_part = getattr(gift, "gift_text", None) or "Подарок прикреплён."
    else:
        gift_part = _format_gift_line(gift)

    lines: list[str] = []
    if llm_reply:
        lines.append(llm_reply)
    lines.append(f"🎄 **Твой подарок:** {gift_part}")

    current_day, _ = current_day_deadline()
    lines.append(_next_prompt_line(current_day))

    return "\n".join(lines)


async def _send_gift_message(target: Message | CallbackQuery, gift, llm_reply: str | None = None) -> None:
    if isinstance(target, CallbackQuery):
        await target.answer()
    caption_text = _gift_caption(gift, llm_reply)
    if not gift or not getattr(gift, "gift_type", None):
        await _respond(target, caption_text)
        return

    gift_type = getattr(gift, "gift_type", GiftType.TEXT)
    media = getattr(gift, "gift_url", None)
    bot, chat_id = _get_bot_and_chat(target)

    if gift_type == GiftType.TEXT or not media:
        await _respond(target, caption_text)
        return

    if gift_type == GiftType.URL:
        await _respond(target, caption_text)
        return

    # Media types: use Telegram send_* APIs
    if gift_type == GiftType.PHOTO:
        await bot.send_photo(chat_id=chat_id, photo=media, caption=caption_text)
    elif gift_type == GiftType.VIDEO:
        await bot.send_video(chat_id=chat_id, video=media, caption=caption_text)
    elif gift_type == GiftType.AUDIO:
        await bot.send_audio(chat_id=chat_id, audio=media, caption=caption_text)
    else:
        await _respond(target, caption_text)


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


@router.message(StateFilter(None), F.photo)
async def admin_photo_gift(message: Message) -> None:
    if message.caption and message.caption.strip().startswith("/set_welcome_image"):
        _set_welcome_image(message.photo[-1].file_id, message.from_user.id, source="photo_command")
        await message.answer("WELCOME_IMAGE_URL обновлён по фото.")
    else:
        await _save_media_gift(message, GiftType.PHOTO)


@router.message(StateFilter(None), F.video)
async def admin_video_gift(message: Message) -> None:
    if message.caption and message.caption.strip().startswith("/set_welcome_image"):
        _set_welcome_image(message.video.file_id, message.from_user.id, source="video_command")
        await message.answer("WELCOME_IMAGE_URL обновлён по видео.")
    else:
        await _save_media_gift(message, GiftType.VIDEO)


@router.message(StateFilter(None), F.audio)
async def admin_audio_gift(message: Message) -> None:
    if message.caption and message.caption.strip().startswith("/set_welcome_image"):
        _set_welcome_image(message.audio.file_id, message.from_user.id, source="audio_command")
        await message.answer("WELCOME_IMAGE_URL обновлён по аудио.")
    else:
        await _save_media_gift(message, GiftType.AUDIO)


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
    welcome_text = (
        "Хо-хо-хо, ну или как там ещё говорят 🎅\n\n"
        "Пока у всех каникулы, у меня — график.\n"
        "Стихотворение приносишь сюда, подарок забираешь отсюда. Всё.\n\n"
        f"Сегодня день {current_campaign_day()}.\n"
        "Давай строки. Я постараюсь быть терпеливым человеком. Насколько это возможно.\n\n"
        "Пиши текстом, голова и так шумит, голоса не могу слушать.\n"
        "Будешь умничать, подарок оставлю себе 🍾\n\n"
        "Погнали.\n\n"
        "И не нужно меня каждый день тыркать, я сам напомню, когда можно 😤"
    )
    if settings.service.welcome_image_url:
        await message.answer_photo(
            settings.service.welcome_image_url,
            caption=welcome_text,
            reply_markup=keyboard,
        )
    else:
        await message.answer(welcome_text, reply_markup=keyboard)


@router.message(StateFilter("*"), Command("set_welcome_image"))
async def cmd_set_welcome_image(message: Message, command: CommandObject, state: FSMContext) -> None:
    if not await _ensure_admin(message):
        return
    if command.args:
        value = command.args.strip()
        _set_welcome_image(value, message.from_user.id, source="command")
        await message.answer("WELCOME_IMAGE_URL обновлён.")
        return

    await state.clear()
    await state.set_state(WelcomeSetupStates.waiting_media)
    await message.answer("Пришли приветственную картинку/видео/аудио (или файл-изображение). /cancel — выйти.", reply_markup=None)


@router.message(StateFilter("*"), Command("setgift"))
async def cmd_setgift(message: Message, command: CommandObject, state: FSMContext) -> None:
    if not await _ensure_admin(message):
        return
    if not command.args:
        await message.answer("Используй: /setgift <day>")
        return
    try:
        day = int(command.args.strip())
    except ValueError:
        await message.answer("День должен быть числом.")
        return
    await state.update_data(day=day)
    await state.set_state(GiftSetupStates.waiting_text)
    await message.answer(
        f"День {day}. Пришли текст подарка. Оставь пустым или /skip, чтобы пропустить текст.",
        reply_markup=None,
    )


@router.message(GiftSetupStates.waiting_text)
async def gift_waiting_text(message: Message, state: FSMContext) -> None:
    if not await _ensure_admin(message):
        await state.clear()
        return
    text_content = message.text
    if text_content is not None:
        stripped = text_content.strip()
        if stripped.lower() in {"", "/skip"}:
            text_content = None
    else:
        text_content = None

    await state.update_data(gift_text=text_content)
    await state.set_state(GiftSetupStates.waiting_media)
    data = await state.get_data()
    day = data.get("day")
    await message.answer(
        f"День {day}. Пришли медиа (фото/видео/аудио или изображение-файл). "
        "Оставь пустым или /skip, чтобы сохранить без медиа.",
        reply_markup=None,
    )


@router.message(GiftSetupStates.waiting_media)
async def gift_waiting_media(message: Message, state: FSMContext) -> None:
    if not await _ensure_admin(message):
        await state.clear()
        return

    data = await state.get_data()
    day = data.get("day")
    gift_text = data.get("gift_text")

    skip_media = False
    if message.text:
        stripped = message.text.strip()
        if stripped.lower() in {"", "/skip"}:
            skip_media = True
        else:
            # Это текст, а не медиа — просим повторить
            await message.answer("Жду медиа (фото/видео/аудио или изображение-файл). Отправь /skip, чтобы без медиа.")
            return

    gift_type: GiftType = GiftType.TEXT
    gift_url: str | None = None

    if not skip_media:
        media_type, media_id = _extract_media_from_message(message)
        if media_type and media_id:
            gift_type = media_type
            gift_url = media_id
        else:
            await message.answer("Не похоже на медиа. Отправь фото/видео/аудио или /skip, чтобы без медиа.")
            return

    gift = await set_gift(day, gift_type, gift_text, gift_url, None)
    await log_error(
        SeverityLevel.INFO,
        "Gift updated",
        {"day": day, "gift_type": gift_type.value, "admin_id": message.from_user.id, "via": "fsm_flow"},
        service_name="gifts",
    )

    caption_text = _gift_caption(gift, None)
    if gift_type == GiftType.PHOTO and gift_url:
        await message.answer_photo(gift_url, caption=caption_text)
    elif gift_type == GiftType.VIDEO and gift_url:
        await message.answer_video(gift_url, caption=caption_text)
    elif gift_type == GiftType.AUDIO and gift_url:
        await message.answer_audio(gift_url, caption=caption_text)
    else:
        await message.answer(caption_text)

    await state.clear()


@router.message(WelcomeSetupStates.waiting_media)
async def welcome_waiting_media(message: Message, state: FSMContext) -> None:
    if not await _ensure_admin(message):
        await state.clear()
        return

    if message.text:
        stripped = message.text.strip()
        if stripped.lower() in {"/cancel", "/skip"}:
            await message.answer("Настройка приветствия отменена.")
            await state.clear()
            return
        else:
            await message.answer("Жду медиа: фото/файл-изображение, видео или аудио. /cancel — выйти.")
            return

    media_type, media_id = _extract_media_from_message(message)
    if not media_type or not media_id:
        await message.answer("Отправь фото/файл-изображение, видео или аудио. /cancel — выйти.")
        return

    _set_welcome_image(media_id, message.from_user.id, source="welcome_fsm")
    preview_caption = (
        "Хо-хо-хо, ну или как там ещё говорят 🎅\n\n"
        "Пока у всех каникулы, у меня — график.\n"
        "Стихотворение приносишь сюда, подарок забираешь отсюда. Всё.\n\n"
        f"Сегодня день {current_campaign_day()}.\n"
        "Давай строки. Я постараюсь быть терпеливым человеком. Насколько это возможно.\n\n"
        "Пиши текстом, голова и так шумит, голоса не могу слушать.\n"
        "Будешь умничать, подарок оставлю себе 🍾\n\n"
        "Погнали.\n\n"
        "И не нужно меня каждый день тыркать, я сам напомню, когда можно 😤"
    )
    if media_type == GiftType.PHOTO:
        await message.answer_photo(media_id, caption=preview_caption)
    elif media_type == GiftType.VIDEO:
        await message.answer_video(media_id, caption=preview_caption)
    elif media_type == GiftType.AUDIO:
        await message.answer_audio(media_id, caption=preview_caption)
    else:
        await message.answer(preview_caption)
    await state.clear()


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
    try:
        day, gift_type, gift_text, gift_url, payload_data = _parse_set_gift_args(command.args or "")
    except GiftParseError as exc:
        await message.answer(str(exc))
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
        end_dt = quiet_hours_end()
        await _respond(target, f"Я сплю. Жди {end_dt.strftime('%H:%M %Z')}.")
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
        if gift:
            await _send_gift_message(target, gift, llm_reply="На сегодня всё! Держи подарок ещё раз:")
        else:
            await _respond(target, "На сегодня всё! Подарок пока не настроен.")
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


# Игнорируем текст, который выглядит как команда (начинается с "/"), чтобы не перебивать обработчики команд
@router.message(F.text, ~F.text.startswith("/"))
async def process_poem(message: Message, state: FSMContext) -> None:
    # Если это команда (начинается с "/") — уходим, чтобы её обработал командный хендлер
    if message.text and message.text.startswith("/"):
        return
    if message.entities and any(ent.type == "bot_command" for ent in message.entities):
        return
    if is_admin(message.from_user.id):
        current_state = await state.get_state()
        # Если админ сейчас в каком-то FSM-потоке (настройка приветствия/подарка) — не перехватываем
        if current_state:
            return
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
        end_dt = quiet_hours_end()
        await message.answer(f"Я сплю. Жди {end_dt.strftime('%H:%M %Z')}.")
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
            if gift:
                await _send_gift_message(message, gift, llm_reply=llm_result.ded_moroz_reply)
            else:
                await message.answer(f"{llm_result.ded_moroz_reply}\nПодарок пока не настроен.")
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
