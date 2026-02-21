"""Anti-spam middleware: rate-limiting + message deduplication."""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message

from bot.config import settings

logger = logging.getLogger(__name__)


class AntiSpamMiddleware(BaseMiddleware):
    """
    Drops messages when:
    • A user sends more than RATE_LIMIT_MESSAGES within RATE_LIMIT_SECONDS.
    • A user sends the exact same text within DEDUP_SECONDS.
    """

    def __init__(self) -> None:
        super().__init__()
        # user_id → list of timestamps
        self._rate: Dict[int, list[float]] = {}
        # user_id → {md5_hex: timestamp}
        self._dedup: Dict[int, Dict[str, float]] = {}

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message) or not event.from_user:
            return await handler(event, data)

        text = (event.text or "").strip()
        # Never silently drop bot commands like /start. Otherwise user clicks Menu repeatedly
        # and gets "nothing happens", which feels like the bot is broken.
        if text.startswith("/"):
            return await handler(event, data)

        uid = event.from_user.id
        now = time.monotonic()

        # ── Rate limit ───────────────────────────────────────────────
        timestamps = self._rate.setdefault(uid, [])
        cutoff = now - settings.RATE_LIMIT_SECONDS
        timestamps[:] = [t for t in timestamps if t > cutoff]

        if len(timestamps) >= settings.RATE_LIMIT_MESSAGES:
            logger.warning("Rate-limit triggered for user %d", uid)
            return None  # silently drop

        timestamps.append(now)

        # ── Deduplication ────────────────────────────────────────────
        if text:
            h = hashlib.md5(text.encode()).hexdigest()
            bucket = self._dedup.setdefault(uid, {})
            # Prune old entries
            bucket = {
                k: v for k, v in bucket.items()
                if now - v < settings.DEDUP_SECONDS
            }
            self._dedup[uid] = bucket

            if h in bucket:
                logger.warning("Duplicate message from user %d", uid)
                return None  # silently drop

            bucket[h] = now

        return await handler(event, data)
