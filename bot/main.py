"""TE GROUP Telegram Bot — entry point.

Resilience features:
1. Auto-restart polling on crash (up to 100 retries with backoff).
2. Keepalive pinger prevents Render free-tier spin-down.
3. Periodic DB health check with auto-reconnect.
4. Bot starts even if the database is unreachable.
5. Bot description / short description set on every start for branding.
6. Health-check HTTP server for Render.
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


# ═══════════════════════════════════════════════════════════════
# HTTP health server
# ═══════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════
# Keepalive pinger — prevents Render free-tier spin-down
# ═══════════════════════════════════════════════════════════════

async def _keepalive_pinger() -> None:
    """Ping our own /health endpoint every 4 minutes.

    Render free-tier spins down a web service after ~15 min of no
    inbound HTTP traffic.  This self-ping keeps the container alive
    so that long-polling never stops.
    """
    import aiohttp

    logger = logging.getLogger("keepalive")

    # Render sets RENDER_EXTERNAL_HOSTNAME automatically
    ext_host = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "")
    if ext_host:
        url = f"https://{ext_host}/health"
    else:
        port = int(os.environ.get("PORT", "10000"))
        url = f"http://127.0.0.1:{port}/health"

    logger.info("Keepalive → %s (every 4 min)", url)

    while True:
        await asyncio.sleep(240)          # 4 minutes
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as sess:
                async with sess.get(url) as resp:
                    logger.debug("keepalive ping: %d", resp.status)
        except Exception as exc:
            logger.warning("keepalive ping failed: %s", exc)


# ═══════════════════════════════════════════════════════════════
# Periodic DB health check
# ═══════════════════════════════════════════════════════════════

async def _db_health_loop() -> None:
    """Every 60 s check that the DB pool is alive.

    If the connection is dead, close the pool and trigger reconnect
    via init_db() which already has retry logic.
    """
    from bot import db as db_mod

    logger = logging.getLogger("db.health")

    while True:
        await asyncio.sleep(60)
        if db_mod.pool is None:
            # init_db / _retry_connect is probably already handling this
            continue
        try:
            async with db_mod.pool.acquire(timeout=5) as conn:
                await conn.fetchval("SELECT 1")
        except Exception as exc:
            logger.error("DB health check failed: %s — reconnecting", exc)
            try:
                await db_mod.pool.close()
            except Exception:
                pass
            db_mod.pool = None
            # Re-init in background (has its own retry loop)
            asyncio.create_task(init_db())


# ═══════════════════════════════════════════════════════════════
# Bot branding
# ═══════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

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

    # Background keepalive — prevents Render free-tier from spinning down
    asyncio.create_task(_keepalive_pinger())

    # Background DB health monitor
    asyncio.create_task(_db_health_loop())

    # ── Polling with auto-restart ─────────────────────────────
    MAX_RETRIES = 100
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            await bot.delete_webhook(drop_pending_updates=False)
            logger.info("Polling started (attempt #%d)", attempt)
            await dp.start_polling(
                bot,
                polling_timeout=30,      # seconds between getUpdates
                handle_signals=False,     # we handle lifecycle ourselves
            )
            # If start_polling returns cleanly → normal shutdown
            logger.info("Polling stopped cleanly")
            break

        except Exception as exc:
            logger.error(
                "Polling crashed (attempt #%d/%d): %s",
                attempt, MAX_RETRIES, exc,
                exc_info=True,
            )
            if attempt < MAX_RETRIES:
                wait = min(attempt * 5, 60)   # 5s → 10s → … → cap at 60s
                logger.info("Restarting polling in %ds…", wait)
                await asyncio.sleep(wait)
            else:
                logger.critical("Max retries (%d) reached — exiting", MAX_RETRIES)

    # Cleanup
    await close_db()
    await bot.session.close()
    logger.info("Bot stopped")


if __name__ == "__main__":
    asyncio.run(main())
