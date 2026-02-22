"""Common handlers: /help + global error handler."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import ErrorEvent, Message

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "ℹ️ <b>TE GROUP — Бот логистики</b>\n\n"
        "🔹 /start — Новая заявка\n"
        "🔹 /help  — Помощь\n\n"
        "По вопросам: <b>info@tegroup.cc</b>\n"
        "Сайт: tegroup.cc"
    )


@router.error()
async def global_error_handler(event: ErrorEvent) -> None:
    logger.error(
        "Unhandled error in update %s: %s",
        event.update.update_id if event.update else "?",
        event.exception,
        exc_info=event.exception,
    )
