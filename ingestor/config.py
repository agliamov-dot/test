from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass
class Config:
    db_dsn: str
    user_agent: str = "CompanyBot/1.0"
    default_fetch_every_minutes: int = 60


def load_config() -> Config:
    return Config(
        db_dsn=os.getenv(
            "DB_DSN", "postgresql+psycopg2://rss:rsspass@localhost:5432/rssdb"
        ),
        user_agent=os.getenv("USER_AGENT", "CompanyBot/1.0"),
        default_fetch_every_minutes=int(os.getenv("DEFAULT_FETCH_EVERY_MINUTES", "60")),
    )
