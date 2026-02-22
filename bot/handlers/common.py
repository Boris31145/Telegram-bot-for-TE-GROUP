"""Common handlers: /start, /help, error handler, fallback forwarder."""

from __future__ import annotations

import html
import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import ErrorEvent, Message

from bot.config import settings
from bot.keyboards import service_kb
from bot.states import OrderForm

logger = logging.getLogger(__name__)
router = Router()
fallback_router = Router()

# ── Visual constants ─────────────────────────────────────────
_DIV = "━" * 20

WELCOME_TEXT = (
    "🏢  <b>TE GROUP</b>\n"
    f"{_DIV}\n\n"
    "Импорт товаров <b>в Россию</b>\n"
    "через ЕАЭС · Кыргызстан\n\n"
    "✓ Самые низкие ставки таможни в ЕАЭС\n"
    "✓ Свободная продажа в РФ без повторной растаможки\n"
    "✓ Доставка из Китая, Турции, ОАЭ, Израиля\n"
    "✓ Полностью легально, все документы\n\n"
    f"{_DIV}\n"
    "👇 <b>Чем можем помочь?</b>"
)


# ═══════════════════════════════════════════════════════════════
# /start
# ═══════════════════════════════════════════════════════════════

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    try:
        msg = await message.answer(WELCOME_TEXT, reply_markup=service_kb())
        await state.update_data(card_id=msg.message_id)
        await state.set_state(OrderForm.service)
    except Exception as exc:
        logger.error("/start failed: %s", exc)
        await message.answer(
            "Бот временно недоступен. Попробуйте через минуту\n"
            "или напишите info@tegroup.cc",
            parse_mode=None,
        )


@router.message(F.text.regexp(r"(?i)^(start|старт|начать|привет)$"))
async def text_start(message: Message, state: FSMContext) -> None:
    await cmd_start(message, state)


# ═══════════════════════════════════════════════════════════════
# /help
# ═══════════════════════════════════════════════════════════════

@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "🏢 <b>TE GROUP — Бот логистики</b>\n\n"
        "▸ /start — Новая заявка\n"
        "▸ /help — Помощь\n\n"
        "📲 WhatsApp: +996 501 989 469\n"
        "🌐 tegroup.cc",
    )


# ═══════════════════════════════════════════════════════════════
# Global error handler
# ═══════════════════════════════════════════════════════════════

@router.error()
async def global_error_handler(event: ErrorEvent) -> None:
    logger.error(
        "Unhandled error in update %s: %s",
        event.update.update_id if event.update else "?",
        event.exception,
        exc_info=event.exception,
    )


# ═══════════════════════════════════════════════════════════════
# Fallback — forward unhandled messages to admins
# ═══════════════════════════════════════════════════════════════

@fallback_router.message()
async def fallback_forward(message: Message, bot: Bot) -> None:
    user = message.from_user
    if not user:
        return

    header = (
        f"💬 Сообщение от клиента\n"
        f"{'=' * 30}\n"
        f"Имя: {user.full_name or ''}"
        f"{(' (@' + user.username + ')') if user.username else ''}\n"
        f"ID: {user.id}\n"
        f"{'=' * 30}"
    )

    for admin_id in settings.admin_ids:
        try:
            await bot.send_message(admin_id, header, parse_mode=None)
            await message.forward(admin_id)
        except Exception as exc:
            logger.error("Forward to admin %s failed: %s", admin_id, exc)

    await message.answer(
        "✉️ <b>Сообщение получено!</b>\n\n"
        "Менеджер ответит вам в ближайшее время.\n"
        "Для оформления заявки — /start",
    )
