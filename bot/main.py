"""
TE GROUP Telegram Bot — entry point.

Works on Render.com (worker) and fly.io (with health-check).
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


# ── Health-check server (Render.com / fly.io) ───────────────────────

async def _start_health_server() -> None:
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


# ── Main ─────────────────────────────────────────────────────────────

async def main() -> None:
    _setup_logging()
    logger = logging.getLogger("bot")
    logger.info("Starting TE GROUP Bot")

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

    # Health-check server (Render / fly.io need an HTTP endpoint)
    await _start_health_server()
    logger.info("Health server on :%s", os.environ.get("PORT", "10000"))

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
