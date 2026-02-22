"""Common handlers: /start, /help, error handler, fallback forwarder.

The fallback_router also includes a CATCH-ALL for callback queries
so that when FSM state is lost (e.g. after a Render restart),
inline-button presses don't silently disappear.
"""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, ErrorEvent, Message, ReplyKeyboardRemove

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
        # Remove any leftover reply keyboard (e.g. phone share button)
        await message.answer("⏳", reply_markup=ReplyKeyboardRemove())
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


@router.message(F.text.regexp(r"(?i)^(start|старт|начать|привет|меню|menu)$"))
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
# FALLBACK — catch-all for expired/lost sessions
# ═══════════════════════════════════════════════════════════════

@fallback_router.callback_query()
async def expired_callback(cb: CallbackQuery, state: FSMContext) -> None:
    """Handle any callback that wasn't caught by FSM-state handlers.

    This happens when the bot restarts and MemoryStorage is wiped —
    all inline-button presses from before the restart lose context.
    We recover gracefully by restarting the conversation.
    """
    logger.info(
        "Expired/unmatched callback from user %s: %s",
        cb.from_user.id, cb.data,
    )
    await cb.answer("⏳ Сессия истекла — начинаем заново", show_alert=False)
    try:
        msg = await cb.message.answer(  # type: ignore[union-attr]
            WELCOME_TEXT, reply_markup=service_kb(),
        )
        await state.clear()
        await state.update_data(card_id=msg.message_id)
        await state.set_state(OrderForm.service)
    except Exception as exc:
        logger.error("Recovery after expired callback failed: %s", exc)


@fallback_router.message()
async def fallback_forward(message: Message, bot: Bot, state: FSMContext) -> None:
    """Forward any unhandled messages to admins.

    Also handles the case where a user is mid-funnel but the bot restarted
    and the FSM state is lost — the user's text message won't match any
    state handler and lands here.
    """
    user = message.from_user
    if not user:
        return

    # Remove any stale reply keyboard
    try:
        await message.answer("⏳", reply_markup=ReplyKeyboardRemove())
    except Exception:
        pass

    header = (
        f"💬 Сообщение от клиента\n"
        f"{'=' * 30}\n"
        f"Имя: {user.full_name or ''}"
        f"{(' (@' + user.username + ')') if user.username else ''}\n"
        f"ID: {user.id}\n"
        f"{'=' * 30}"
    )

    forwarded = False
    for admin_id in settings.admin_ids:
        try:
            await bot.send_message(admin_id, header, parse_mode=None)
            await message.forward(admin_id)
            forwarded = True
        except Exception as exc:
            logger.error("Forward to admin %s failed: %s", admin_id, exc)

    if forwarded:
        await message.answer(
            "✉️ <b>Сообщение получено!</b>\n\n"
            "Менеджер ответит вам в ближайшее время.\n\n"
            "Для оформления заявки — /start",
        )
    else:
        await message.answer(
            "✉️ <b>Сообщение получено!</b>\n\n"
            "Для оформления заявки нажмите /start",
        )
