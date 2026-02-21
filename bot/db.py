"""Database layer — asyncpg connection pool + CRUD for leads."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import asyncpg

from bot.config import settings

logger = logging.getLogger(__name__)

pool: asyncpg.Pool | None = None


# ── Lifecycle ────────────────────────────────────────────────────────

async def init_db() -> None:
    """Create the connection pool and run migrations."""
    global pool
    pool = await asyncpg.create_pool(
        settings.DATABASE_URL,
        min_size=2,
        max_size=10,
    )
    migration = Path(__file__).resolve().parent.parent / "migrations" / "001_init.sql"
    async with pool.acquire() as conn:
        await conn.execute(migration.read_text(encoding="utf-8"))
    logger.info("Database initialised, migration applied")


async def close_db() -> None:
    global pool
    if pool:
        await pool.close()
        pool = None
        logger.info("Database connection closed")


# ── CRUD ─────────────────────────────────────────────────────────────

async def save_lead(data: dict[str, Any]) -> int:
    """Insert a new lead and return its ID."""
    async with pool.acquire() as conn:  # type: ignore[union-attr]
        row = await conn.fetchrow(
            """
            INSERT INTO leads
                (telegram_id, username, full_name, country, city_from,
                 cargo_type, weight_kg, volume_m3, urgency, incoterms,
                 phone, comment, status)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,'NEW')
            RETURNING id
            """,
            data["telegram_id"],
            data.get("username", ""),
            data.get("full_name", ""),
            data["country"],
            data.get("city_from", ""),
            data.get("cargo_type", ""),
            data.get("weight_kg", 0),
            data.get("volume_m3", 0),
            data.get("urgency", ""),
            data.get("incoterms", ""),
            data.get("phone", ""),
            data.get("comment", ""),
        )
        return row["id"]  # type: ignore[index]


async def get_lead(lead_id: int) -> dict[str, Any] | None:
    async with pool.acquire() as conn:  # type: ignore[union-attr]
        row = await conn.fetchrow("SELECT * FROM leads WHERE id = $1", lead_id)
        return dict(row) if row else None


async def get_leads(limit: int = 10) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:  # type: ignore[union-attr]
        rows = await conn.fetch(
            "SELECT * FROM leads ORDER BY created_at DESC LIMIT $1", limit
        )
        return [dict(r) for r in rows]


async def update_lead_status(lead_id: int, status: str) -> bool:
    async with pool.acquire() as conn:  # type: ignore[union-attr]
        result = await conn.execute(
            "UPDATE leads SET status = $1, updated_at = NOW() WHERE id = $2",
            status,
            lead_id,
        )
        return result == "UPDATE 1"


async def export_all_leads() -> list[dict[str, Any]]:
    async with pool.acquire() as conn:  # type: ignore[union-attr]
        rows = await conn.fetch("SELECT * FROM leads ORDER BY created_at DESC")
        return [dict(r) for r in rows]
