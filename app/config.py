"""Application settings loaded from environment variables and `.env` (pydantic-settings)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from pymongo.uri_parser import parse_uri

BASE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["development", "production", "test"] = "development"
    app_base_url: str = "http://localhost:9000"
    port: int = 9000

    mongo_uri: str
    mongo_db_name: str | None = None
    mongo_timeout_ms: int = Field(default=5000, ge=100, le=60000)

    secret_key: str = Field(min_length=32)
    cookie_secure: bool = True
    session_ttl_days: int = Field(default=7, ge=1, le=90)
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)

    upload_dir: Path = Path("uploads")
    max_upload_mb: int = Field(default=5, ge=1, le=50)
    max_body_mb: int = Field(default=10, ge=1, le=100)
    admin_orders_page_size: int = Field(default=25, ge=5, le=200)
    display_timezone: str = "Asia/Kolkata"
    log_level: str = "INFO"

    whatsapp_number: str = "919288245292"
    free_delivery_threshold: float = 1099
    business_phone: str = "+91 92882 45292"
    business_email: str = "akroyalflames@gmail.com"
    business_address: str = "Delhi, India"
    business_hours: str = "Monday - Sunday: 9:00 AM - 9:00 PM"
    instagram_url: str = "https://www.instagram.com/akroyalflames/"
    instagram_handle: str = "@akroyalflames"
    facebook_url: str = "https://www.facebook.com/"
    youtube_video_id: str = "dJJCayBThvY"
    map_embed_url: str = ""

    rate_limit_login_per_15m: int = 5
    rate_limit_login_ip_per_15m: int = 30
    rate_limit_register_per_hour: int = 10

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip().rstrip("/") for part in value.split(",") if part.strip()]
        return value

    @field_validator("app_base_url")
    @classmethod
    def _strip_base(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("display_timezone")
    @classmethod
    def _valid_tz(cls, value: str) -> str:
        ZoneInfo(value)
        return value

    @field_validator("whatsapp_number")
    @classmethod
    def _digits_only(cls, value: str) -> str:
        if not value.isdigit():
            raise ValueError("WHATSAPP_NUMBER must contain digits only")
        return value

    @field_validator("map_embed_url")
    @classmethod
    def _map_url(cls, value: str) -> str:
        if value and not value.startswith("https://www.google.com/maps/embed"):
            raise ValueError("MAP_EMBED_URL must start with https://www.google.com/maps/embed")
        return value

    @property
    def database_name(self) -> str:
        """MONGO_DB_NAME overrides; otherwise the URI path; otherwise Mongoose's default `test`."""
        if self.mongo_db_name:
            return self.mongo_db_name
        return parse_uri(self.mongo_uri).get("database") or "test"

    @property
    def base_origin(self) -> str:
        parts = urlsplit(self.app_base_url)
        return f"{parts.scheme}://{parts.netloc}"

    @property
    def allowed_origins(self) -> set[str]:
        return {self.base_origin, *self.cors_origins}

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def max_body_bytes(self) -> int:
        return self.max_body_mb * 1024 * 1024

    @property
    def session_ttl_seconds(self) -> int:
        return self.session_ttl_days * 24 * 60 * 60

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.display_timezone)

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
