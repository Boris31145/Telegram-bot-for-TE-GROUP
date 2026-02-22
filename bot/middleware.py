"""Anti-spam middleware: rate-limiting + deduplication.

Commands (messages starting with /) and contact shares always pass through.
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


class AntiSpamMiddleware(BaseMiddleware):
    def __init__(self) -> None:
        super().__init__()
        self._rate: Dict[int, list[float]] = {}
        self._dedup: Dict[int, Dict[str, float]] = {}

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

        # Rate limit
        timestamps = self._rate.setdefault(uid, [])
        cutoff = now - settings.RATE_LIMIT_SECONDS
        timestamps[:] = [t for t in timestamps if t > cutoff]
        if len(timestamps) >= settings.RATE_LIMIT_MESSAGES:
            logger.warning("Rate-limit: user %d", uid)
            return None
        timestamps.append(now)

        # Dedup
        if event.text:
            h = hashlib.md5(event.text.encode()).hexdigest()
            bucket = self._dedup.setdefault(uid, {})
            bucket = {k: v for k, v in bucket.items() if now - v < settings.DEDUP_SECONDS}
            self._dedup[uid] = bucket
            if h in bucket:
                logger.warning("Dedup: user %d", uid)
                return None
            bucket[h] = now

        return await handler(event, data)
