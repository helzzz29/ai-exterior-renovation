from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(ROOT_DIR / ".env", ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    env: Literal["dev", "test", "prod"] = "dev"

    # external services (the only two secrets)
    gemini_api_key: str = ""
    jev_api_key: str = ""

    # "real" calls Gemini + Jev; "fake" replays recorded fixtures (tests only)
    ai_provider: Literal["real", "fake"] = "real"
    gemini_segment_model: str = "gemini-3.8-flash"
    gemini_image_model: str = "gemini-nano-banana-2.1"
    jev_model: str = "jev-latest"
    gemini_max_concurrency: int = 2
    jev_max_concurrency: int = 8

    # thresholds
    region_confidence_threshold: float = 0.6
    render_qa_threshold: float = 0.6
    render_max_auto_regenerate: int = 2

    database_url: str = "postgresql+asyncpg://reno:reno@localhost:5433/reno"
    storage_root: Path = ROOT_DIR / "data"
    seed_dir: Path = ROOT_DIR / "seed"

    # where photos, new looks and reports live: "local" (storage_root) or any S3-compatible
    # bucket (Backblaze B2 in production). Keys are the same either way.
    storage_backend: Literal["local", "s3"] = "local"
    s3_endpoint_url: str = ""
    s3_region: str = ""
    s3_bucket: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""

    # server (production runs one process: API + background worker + built website)
    host: str = "127.0.0.1"
    port: int = 8000
    run_worker: bool = False
    web_dist: Path | None = None

    jwt_secret: str = "dev-only-change-me"
    jwt_ttl_hours: int = 72
    cors_origins: list[str] = ["http://localhost:5173"]

    max_upload_bytes: int = 15 * 1024 * 1024

    # accounts: production is invite-only. seed_users = {email: argon2 hash}, created or
    # updated on start-up; plain passwords never reach the server's settings.
    signup_open: bool = True
    seed_users: dict[str, str] = {}

    # per person, per day (UTC); 0 = no limit. Protects the paid AI keys on a public link.
    daily_photo_limit: int = 0
    daily_new_look_limit: int = 0

    # background jobs (Procrastinate). Whole-job retries with exponential backoff.
    job_max_attempts: int = 3
    job_retry_base_seconds: float = 2.0
    worker_concurrency: int = 4

    log_level: str = "INFO"
    log_json: bool = True

    @field_validator("database_url")
    @classmethod
    def _asyncpg_url(cls, url: str) -> str:
        """Accept a plain `postgresql://...?sslmode=require` URL (as Neon gives it) or driver schemes."""
        for prefix in (
            "postgresql+psycopg2://",
            "postgresql+psycopg://",
            "postgresql://",
            "postgres://",
        ):
            if url.startswith(prefix):
                url = "postgresql+asyncpg://" + url[len(prefix) :]
                break
        base, _, query = url.partition("?")
        params = []
        for part in filter(None, query.split("&")):
            key, _, value = part.partition("=")
            if key == "channel_binding":  # libpq-only option; asyncpg rejects it
                continue
            params.append(f"ssl={value}" if key == "sslmode" else part)
        return base + ("?" + "&".join(params) if params else "")

    @property
    def queue_dsn(self) -> str:
        """libpq/psycopg DSN for Procrastinate (same database as SQLAlchemy)."""
        url = self.database_url
        for prefix in (
            "postgresql+asyncpg://",
            "postgresql+psycopg2://",
            "postgresql+psycopg://",
            "postgres://",
        ):
            if url.startswith(prefix):
                url = "postgresql://" + url[len(prefix) :]
                break
        base, _, query = url.partition("?")
        parts = filter(None, query.split("&"))
        params = ["sslmode=" + p[4:] if p.startswith("ssl=") else p for p in parts]
        return base + ("?" + "&".join(params) if params else "")


@lru_cache
def get_settings() -> Settings:
    return Settings()
