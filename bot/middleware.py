"""Anti-spam middleware: rate-limiting + deduplication.

Commands (messages starting with /) and contact shares always pass through.
Short messages (< 30 chars) skip dedup — they are likely form inputs
(phone numbers, city names, weights, etc.) that users may need to re-enter.
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message

from bot.config import settings

logger = logging.getLogger(__name__)

# Messages shorter than this skip dedup (form inputs: phones, cities, numbers)
_DEDUP_MIN_LENGTH = 30


class AntiSpamMiddleware(BaseMiddleware):
    def __init__(self) -> None:
        super().__init__()
        self._rate: Dict[int, list[float]] = {}
        self._dedup: Dict[int, Dict[str, float]] = {}
        self._last_cleanup: float = 0.0

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message) or not event.from_user:
            return await handler(event, data)

        # Always let commands and contacts through
        if event.text and event.text.startswith("/"):
            return await handler(event, data)
        if event.contact:
            return await handler(event, data)

        uid = event.from_user.id
        now = time.monotonic()

        # Periodic cleanup — every 5 minutes, purge stale entries
        if now - self._last_cleanup > 300:
            self._cleanup(now)
            self._last_cleanup = now

        # Rate limit
        timestamps = self._rate.setdefault(uid, [])
        cutoff = now - settings.RATE_LIMIT_SECONDS
        timestamps[:] = [t for t in timestamps if t > cutoff]
        if len(timestamps) >= settings.RATE_LIMIT_MESSAGES:
            logger.warning("Rate-limit: user %d", uid)
            return None
        timestamps.append(now)

        # Dedup — only for longer messages (not form inputs like phone numbers)
        text = event.text or ""
        if len(text) >= _DEDUP_MIN_LENGTH:
            h = hashlib.md5(text.encode()).hexdigest()
            bucket = self._dedup.setdefault(uid, {})
            # Purge expired entries for this user
            bucket = {k: v for k, v in bucket.items() if now - v < settings.DEDUP_SECONDS}
            self._dedup[uid] = bucket
            if h in bucket:
                logger.warning("Dedup: user %d (msg len=%d)", uid, len(text))
                return None
            bucket[h] = now

        return await handler(event, data)

    def _cleanup(self, now: float) -> None:
        """Remove stale users from rate/dedup dicts to prevent memory leaks."""
        stale_rate = [
            uid for uid, ts in self._rate.items()
            if not ts or (now - ts[-1]) > settings.RATE_LIMIT_SECONDS * 10
        ]
        for uid in stale_rate:
            del self._rate[uid]

        stale_dedup = [
            uid for uid, bucket in self._dedup.items()
            if not bucket
        ]
        for uid in stale_dedup:
            del self._dedup[uid]
