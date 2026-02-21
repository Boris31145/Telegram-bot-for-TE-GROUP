"""Application settings — loaded from environment variables / .env file."""

from __future__ import annotations

from typing import List

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Telegram
    BOT_TOKEN: str

    # Postgres
    DATABASE_URL: str

    # Comma-separated Telegram user IDs that have admin access
    ADMIN_CHAT_ID: str

    # Logging
    LOG_LEVEL: str = "INFO"

    # Anti-spam
    RATE_LIMIT_MESSAGES: int = 3
    RATE_LIMIT_SECONDS: int = 5
    DEDUP_SECONDS: int = 30

    @property
    def admin_ids(self) -> List[int]:
        """Parse comma-separated admin IDs into a list of ints."""
        return [int(x.strip()) for x in self.ADMIN_CHAT_ID.split(",") if x.strip()]

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
