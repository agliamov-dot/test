from __future__ import annotations

import os
from datetime import date
from typing import List

from pydantic import BaseModel, Field, AliasChoices, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

if os.path.exists(".env"):
    load_dotenv()


class CampaignConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    start_date: date = Field(..., validation_alias=AliasChoices("CAMPAIGN_START_DATE"))
    days: int = Field(
        24, validation_alias=AliasChoices("CAMPAIGN_DAYS", "CAMPAIGN_TOTAL_DAYS")
    )
    reminder_deadline_hour: int = Field(
        10, validation_alias=AliasChoices("CAMPAIGN_REMINDER_DEADLINE_HOUR", "CAMPAIGN_REMINDER_HOUR")
    )
    missed_deadline_hour: int = Field(
        22, validation_alias=AliasChoices("CAMPAIGN_MISSED_DEADLINE_HOUR", "CAMPAIGN_MISSED_HOUR")
    )
    timezone: str = Field("UTC", validation_alias=AliasChoices("CAMPAIGN_TZ", "CAMPAIGN_TIMEZONE"))
    quiet_hours_start: int = Field(23, validation_alias=AliasChoices("CAMPAIGN_QUIET_HOURS_START"))
    quiet_hours_end: int = Field(8, validation_alias=AliasChoices("CAMPAIGN_QUIET_HOURS_END"))
    max_attempts_per_day: int = Field(
        3, validation_alias=AliasChoices("CAMPAIGN_MAX_ATTEMPTS_PER_DAY", "MAX_ATTEMPTS_PER_DAY")
    )

    @field_validator(
        "reminder_deadline_hour",
        "missed_deadline_hour",
        "quiet_hours_start",
        "quiet_hours_end",
    )
    @classmethod
    def _validate_hour(cls, value: int) -> int:
        if not 0 <= value <= 23:
            raise ValueError("Hour must be between 0 and 23")
        return value

    @field_validator("days")
    @classmethod
    def _validate_days(cls, value: int) -> int:
        if value < 1:
            raise ValueError("Campaign days must be positive")
        return value


class OpenRouterConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="OPENROUTER_", extra="ignore")

    api_key: str
    base_url: str = "https://openrouter.ai/api/v1"
    model: str = "openai/gpt-4o-mini-2024-07-18"


class DatabaseConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="DATABASE_", extra="ignore")

    url: str


class AdminConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="ADMIN_", extra="ignore")

    admin_ids: List[int] = Field(
        default_factory=list,
        validation_alias=AliasChoices(
            "IDS",            # стандартный alias с префиксом ADMIN_
            "ADMIN_IDS",      # без префикса (часто задавали так)
            "ADMINS__IDS",    # вложенный синтаксис pydantic settings
            "ADMIN_ADMIN_IDS" # префикс + имя поля
        ),
    )

    @field_validator("admin_ids", mode="before")
    @classmethod
    def _split_ids(cls, value: str | list[int]) -> list[int]:
        if isinstance(value, list):
            return value
        if not value:
            return []
        return [int(item.strip()) for item in value.split(",") if item.strip()]


class ServiceConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    bot_token: str = Field(..., alias="BOT_TOKEN")
    redis_dsn: str | None = Field(None, alias="REDIS_DSN")
    chunk_size: int = Field(100, alias="BATCH_CHUNK_SIZE")


class Settings(BaseModel):
    env: str = Field(default_factory=lambda: os.getenv("ENV", "local"))
    campaign: CampaignConfig = Field(default_factory=CampaignConfig)
    openrouter: OpenRouterConfig = Field(default_factory=OpenRouterConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    admins: AdminConfig = Field(default_factory=AdminConfig)
    service: ServiceConfig = Field(default_factory=ServiceConfig)


settings = Settings()
