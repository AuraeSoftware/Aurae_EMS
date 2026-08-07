import os
from pydantic_settings import BaseSettings
from typing import Optional


def _build_url() -> str:
    raw = os.environ.get("APP_DATABASE_URL", "") or os.environ.get("DATABASE_URL", "").strip()
    if not raw and os.environ.get("PGHOST"):
        raw = "postgresql://{user}:{pw}@{host}:{port}/{db}".format(
            user=os.environ.get("PGUSER", "postgres"),
            pw=os.environ.get("PGPASSWORD", ""),
            host=os.environ.get("PGHOST", "localhost"),
            port=os.environ.get("PGPORT", "5432"),
            db=os.environ.get("PGDATABASE", "railway"),
        )
    if not raw:
        return "postgresql+asyncpg://aurae_admin:aurae_secret@localhost:5432/aurae_ems"
    if raw.startswith("postgres://"):
        return "postgresql+asyncpg://" + raw[len("postgres://"):]
    if raw.startswith("postgresql://") and "+asyncpg" not in raw:
        return "postgresql+asyncpg://" + raw[len("postgresql://"):]
    return raw


def _build_sync_url() -> str:
    url = _build_url()
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


class Settings(BaseSettings):
    DATABASE_URL: str = _build_url()
    SYNC_DATABASE_URL: str = _build_sync_url()
    SECRET_KEY: str = os.environ.get("SECRET_KEY", "change-this-secret")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.environ.get("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

    AXIS_BASE_URL: str = "https://apiportal.axisbank.co.in"
    AXIS_CLIENT_ID: Optional[str] = None
    AXIS_CLIENT_SECRET: Optional[str] = None
    AXIS_CORPORATE_ID: Optional[str] = None
    AXIS_ACCOUNT_NUMBER: str = os.environ.get("AXIS_ACCOUNT_NUMBER", "9220000000001")

    REDIS_URL: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    CORS_ORIGINS: str = os.environ.get(
        "CORS_ORIGINS",
        "http://localhost,http://localhost:3000"  # TODO: add Aurae's deployed frontend URL(s) here (comma-separated)
    )
    SEED_DB: bool = os.environ.get("SEED_DB", "true").lower() == "true"

    model_config = {"extra": "ignore"}

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",")]


settings = Settings()
