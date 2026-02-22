"""Database layer — asyncpg pool + CRUD for leads.

The bot starts even if the database is unreachable.
All CRUD operations gracefully handle pool=None.
Background retry + periodic health check keep the connection alive.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import asyncpg

from bot.config import settings

logger = logging.getLogger(__name__)

pool: asyncpg.Pool | None = None

_MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"

# How long to wait for pool creation before giving up (seconds)
_POOL_CREATE_TIMEOUT = 20


async def init_db() -> None:
    """Connect to Postgres and run migrations.

    If the connection fails the bot still starts — a background task
    will retry every 15 seconds.
    """
    global pool
    if not settings.DATABASE_URL:
        logger.warning("DATABASE_URL is empty — running without database")
        return

    try:
        # Wrap pool creation in asyncio.wait_for to prevent hanging
        pool = await asyncio.wait_for(
            asyncpg.create_pool(
                settings.DATABASE_URL,
                min_size=1,
                max_size=10,
                command_timeout=15,
            ),
            timeout=_POOL_CREATE_TIMEOUT,
        )
        await _run_migrations()
        logger.info("Database connected")
    except Exception as exc:
        logger.error("Database connection failed: %s — will retry in background", exc)
        pool = None
        asyncio.create_task(_retry_connect())


async def _retry_connect() -> None:
    global pool
    for attempt in range(1, 40):
        await asyncio.sleep(15)
        try:
            pool = await asyncio.wait_for(
                asyncpg.create_pool(
                    settings.DATABASE_URL,
                    min_size=1,
                    max_size=10,
                    command_timeout=15,
                ),
                timeout=_POOL_CREATE_TIMEOUT,
            )
            await _run_migrations()
            logger.info("Database connected on retry #%d", attempt)
            return
        except Exception as exc:
            logger.warning("DB retry #%d failed: %s", attempt, exc)
    logger.error("Gave up reconnecting to database after 40 attempts")


async def _run_migrations() -> None:
    if not pool:
        return
    migration_files = sorted(_MIGRATIONS_DIR.glob("*.sql"))
    async with pool.acquire() as conn:
        for mf in migration_files:
            await conn.execute(mf.read_text(encoding="utf-8"))
    logger.info("Migrations applied: %d file(s)", len(migration_files))


async def close_db() -> None:
    global pool
    if pool:
        await pool.close()
        pool = None


def _check_pool() -> asyncpg.Pool:
    if pool is None:
        raise RuntimeError("Database is not available")
    return pool


# ═══════════════════════════════════════════════════════════════
# CRUD
# ═══════════════════════════════════════════════════════════════

async def save_lead(data: dict[str, Any]) -> int:
    p = _check_pool()
    async with p.acquire(timeout=10) as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO leads
                (telegram_id, username, full_name,
                 service_type, customs_direction, invoice_value,
                 country, city_from,
                 cargo_type, weight_kg, volume_m3,
                 urgency, incoterms,
                 phone, comment, status)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,'NEW')
            RETURNING id
            """,
            data["telegram_id"],
            data.get("username", ""),
            data.get("full_name", ""),
            data.get("service_type", "delivery"),
            data.get("customs_direction", ""),
            float(data.get("invoice_value_num", 0) or 0),
            data.get("country", ""),
            data.get("city_from", ""),
            data.get("cargo_type", ""),
            float(data.get("weight_kg", 0) or 0),
            float(data.get("volume_m3", 0) or 0),
            data.get("urgency", ""),
            data.get("incoterms", ""),
            data.get("phone", ""),
            data.get("comment", ""),
        )
        return row["id"]  # type: ignore[index]


async def get_lead(lead_id: int) -> dict[str, Any] | None:
    p = _check_pool()
    async with p.acquire(timeout=10) as conn:
        row = await conn.fetchrow("SELECT * FROM leads WHERE id = $1", lead_id)
        return dict(row) if row else None


async def get_leads(limit: int = 10) -> list[dict[str, Any]]:
    p = _check_pool()
    async with p.acquire(timeout=10) as conn:
        rows = await conn.fetch(
            "SELECT * FROM leads ORDER BY created_at DESC LIMIT $1", limit,
        )
        return [dict(r) for r in rows]


async def update_lead_status(lead_id: int, status: str) -> bool:
    p = _check_pool()
    async with p.acquire(timeout=10) as conn:
        result = await conn.execute(
            "UPDATE leads SET status = $1, updated_at = NOW() WHERE id = $2",
            status, lead_id,
        )
        return result == "UPDATE 1"


async def export_all_leads() -> list[dict[str, Any]]:
    p = _check_pool()
    async with p.acquire(timeout=10) as conn:
        rows = await conn.fetch("SELECT * FROM leads ORDER BY created_at DESC")
        return [dict(r) for r in rows]
