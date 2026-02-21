"""
T.E. Group Telegram Bot — entry point.

Starts the aiogram long-polling loop and a lightweight
aiohttp health-check server on :8080 (for fly.io).
"""

from __future__ import annotations

import asyncio
import logging
import sys

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from pythonjsonlogger import jsonlogger

from bot.config import settings
from bot.db import close_db, init_db
from bot.handlers import admin, common, funnel
from bot.middleware import AntiSpamMiddleware


# ── Logging ──────────────────────────────────────────────────────────

def _setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    fmt = jsonlogger.JsonFormatter(
        "%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    handler.setFormatter(fmt)
    logging.root.handlers = [handler]
    logging.root.setLevel(settings.LOG_LEVEL)


# ── Health-check server (fly.io) ────────────────────────────────────

async def _health(_request: web.Request) -> web.Response:
    return web.Response(text="ok")


async def _start_health_server() -> None:
    app = web.Application()
    app.router.add_get("/", _health)
    app.router.add_get("/health", _health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()


# ── Main ─────────────────────────────────────────────────────────────

async def main() -> None:
    _setup_logging()
    logger = logging.getLogger("bot")
    logger.info("Starting T.E. Group Bot …")

    # Database
    await init_db()

    # Bot + dispatcher
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Middleware
    dp.message.middleware(AntiSpamMiddleware())

    # Routers (order matters: common first, then admin, then funnel)
    dp.include_router(common.router)
    dp.include_router(admin.router)
    dp.include_router(funnel.router)

    # Health-check for fly.io
    await _start_health_server()
    logger.info("Health server started on :8080")

    # Start long-polling
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Bot polling started")
        await dp.start_polling(bot)
    finally:
        await close_db()
        await bot.session.close()
        logger.info("Bot stopped")


if __name__ == "__main__":
    asyncio.run(main())
