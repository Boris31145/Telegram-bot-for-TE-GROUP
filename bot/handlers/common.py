"""Common handlers: /help, global error handler, fallback forwarder."""

from __future__ import annotations

import html
import logging

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import ErrorEvent, Message

from bot.config import settings

logger = logging.getLogger(__name__)
router = Router()

# A separate router registered LAST — catches all unhandled messages
fallback_router = Router()


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "ℹ️ <b>TE GROUP — Бот логистики</b>\n\n"
        "🔹 /start — Новая заявка\n"
        "🔹 /help  — Помощь\n\n"
        "📲 WhatsApp: +996 501 989 469\n"
        "🌐 Сайт: tegroup.cc"
    )


@router.error()
async def global_error_handler(event: ErrorEvent) -> None:
    logger.error(
        "Unhandled error in update %s: %s",
        event.update.update_id if event.update else "?",
        event.exception,
        exc_info=event.exception,
    )


# ══════════════════════════════════════════════════════════════════
# FALLBACK: forward ANY unhandled text/photo/document to admins
# ══════════════════════════════════════════════════════════════════

@fallback_router.message()
async def fallback_forward_to_admins(message: Message, bot: Bot) -> None:
    """
    If a user writes something outside any flow (no FSM state, no command),
    forward their message to the admin group so managers can respond.
    """
    user = message.from_user
    if not user:
        return

    user_name = html.escape(user.full_name or "")
    username_part = f" (@{html.escape(user.username)})" if user.username else ""
    user_id = user.id

    # Build a notification header (plain text — no HTML issues)
    header = (
        f"💬 Сообщение от клиента\n"
        f"{'=' * 30}\n"
        f"Имя: {user.full_name or ''}{(' (@' + user.username + ')') if user.username else ''}\n"
        f"ID: {user_id}\n"
        f"{'=' * 30}"
    )

    for admin_id in settings.admin_ids:
        try:
            # First send the header
            await bot.send_message(admin_id, header, parse_mode=None)
            # Then forward the original message (preserves photos, docs, etc.)
            await message.forward(admin_id)
            logger.info("Forwarded user message to admin %s", admin_id)
        except Exception as exc:
            logger.error("Failed to forward to admin %s: %s", admin_id, exc)

    # Reply to user
    await message.answer(
        "✉️ <b>Ваше сообщение получено!</b>\n\n"
        "Менеджер ответит вам в ближайшее время.\n\n"
        "Для оформления заявки нажмите /start"
    )
