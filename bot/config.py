"""Application settings — loaded from environment variables / .env file."""

from __future__ import annotations

from typing import List

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    BOT_TOKEN: str
    DATABASE_URL: str = ""
    ADMIN_CHAT_ID: str = ""
    LOG_LEVEL: str = "INFO"

    # Anti-spam
    RATE_LIMIT_MESSAGES: int = 5
    RATE_LIMIT_SECONDS: int = 10
    DEDUP_SECONDS: int = 30

    @property
    def admin_ids(self) -> List[int]:
        return [int(x.strip()) for x in self.ADMIN_CHAT_ID.split(",") if x.strip()]

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
