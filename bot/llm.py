"""LLM client(s) used by the agent router."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from bot.config import settings

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = (
    "Ты — помощник компании TE GROUP (логистика и таможенное оформление). "
    "Отвечай по-русски, коротко и по делу. "
    "Если данных не хватает — задай до 3 уточняющих вопросов списком. "
    "Не выдумывай цены; вместо этого объясни, какие данные нужны для расчёта. "
    "По таможне: давай общий ориентир по документам/процессу и предупреди, что "
    "итоговые требования зависят от товара/страны/кода ТН ВЭД."
)


async def answer_with_openai(user_text: str) -> str | None:
    """Return assistant answer or None if LLM is disabled/unconfigured."""
    if not settings.LLM_ENABLED:
        return None
    if not settings.OPENAI_API_KEY:
        return None

    url = f"{settings.OPENAI_BASE_URL.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "model": settings.OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ],
        "temperature": settings.OPENAI_TEMPERATURE,
        "max_tokens": settings.OPENAI_MAX_TOKENS,
    }

    timeout = aiohttp.ClientTimeout(total=settings.OPENAI_TIMEOUT_SECONDS)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status >= 400:
                    body = await resp.text()
                    logger.warning("OpenAI error %s: %s", resp.status, body[:500])
                    return None
                data = await resp.json()
    except Exception as exc:
        logger.warning("OpenAI request failed: %s", exc)
        return None

    try:
        return (data["choices"][0]["message"]["content"] or "").strip()
    except Exception:
        logger.warning("Unexpected OpenAI response shape: %s", str(data)[:500])
        return None

