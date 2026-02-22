"""TE GROUP Telegram Bot — entry point.

Key design:
- Bot starts even if the database is unreachable (retry in background).
- Never drops pending updates (so messages during restart are processed).
- Bot description / short description set on every start for branding.
- Health-check HTTP server for Render.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from bot.config import settings
from bot.db import close_db, init_db
from bot.handlers import admin, common, funnel
from bot.handlers.common import fallback_router
from bot.middleware import AntiSpamMiddleware


def _setup_logging() -> None:
    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(fmt)
    logging.root.handlers = [handler]
    logging.root.setLevel(settings.LOG_LEVEL)


async def _start_health_server() -> None:
    """Minimal HTTP server so Render knows the service is alive."""
    from aiohttp import web

    async def _health(_r: web.Request) -> web.Response:
        return web.Response(text="ok")

    port = int(os.environ.get("PORT", "10000"))
    app = web.Application()
    app.router.add_get("/", _health)
    app.router.add_get("/health", _health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()


async def _set_bot_branding(bot: Bot) -> None:
    """Set bot description and short description for TE GROUP branding."""
    logger = logging.getLogger("bot")
    try:
        await bot.set_my_description(
            "TE GROUP — Импорт в Россию через ЕАЭС.\n"
            "Расчёт доставки и таможенного оформления.\n\n"
            "🇨🇳 Китай  ·  🇹🇷 Турция\n"
            "🇦🇪 ОАЭ  ·  🇮🇱 Израиль\n\n"
            "📞 РФ: +7 952 778 3680\n"
            "📲 WhatsApp: +996 501 989 469\n\n"
            "Нажмите «Начать» для оформления заявки."
        )
        await bot.set_my_short_description(
            "TE GROUP · Расчёт доставки и таможни — импорт в Россию через ЕАЭС"
        )
        logger.info("Bot branding set")
    except Exception as exc:
        logger.warning("Could not set bot description: %s", exc)


async def main() -> None:
    _setup_logging()
    logger = logging.getLogger("bot")
    logger.info("Starting TE GROUP Bot")

    # Database — non-fatal
    try:
        await init_db()
    except Exception as exc:
        logger.error("init_db raised: %s — bot will start without DB", exc)

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    # Commands & branding
    await bot.set_my_commands([
        BotCommand(command="start", description="📦 Новая заявка"),
        BotCommand(command="help", description="ℹ️ Помощь"),
    ])
    await _set_bot_branding(bot)

    dp = Dispatcher(storage=MemoryStorage())
    dp.message.middleware(AntiSpamMiddleware())

    # Router order matters: common first, then admin, then funnel, fallback last.
    dp.include_router(common.router)
    dp.include_router(admin.router)
    dp.include_router(funnel.router)
    dp.include_router(fallback_router)

    # Health server for Render
    await _start_health_server()
    logger.info("Health server on :%s", os.environ.get("PORT", "10000"))

    try:
        # CRITICAL: drop_pending_updates=False — do NOT lose messages sent during restart
        await bot.delete_webhook(drop_pending_updates=False)
        logger.info("Polling started (pending updates preserved)")
        await dp.start_polling(bot)
    finally:
        await close_db()
        await bot.session.close()
        logger.info("Bot stopped")


if __name__ == "__main__":
    asyncio.run(main())
