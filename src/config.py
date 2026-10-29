from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    MODE: Literal["TEST", "LOCAL", "PROD"] = "LOCAL"
    DB_HOST: str = "localhost"
    DB_PORT: int = 5544
    DB_USER: str = "compas"
    DB_PASS: str
    DB_NAME: str = "compas"
    DB_POOL_SIZE: int = Field(default=5, ge=1)
    DB_MAX_OVERFLOW: int = Field(default=5, ge=0)
    JWT_SECRET_KEY: str = Field(min_length=32)
    JWT_REFRESH_SECRET_KEY: str = Field(min_length=32)
    JWT_ALGORITHM: Literal["HS256"] = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    DATA_ENCRYPTION_KEY: str
    COOKIE_SECURE: bool = False
    LEGACY_AUTH_COOKIES: bool = False
    FRONTEND_URL: AnyHttpUrl | None = None
    ALLOWED_ORIGINS: list[str] = []
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""
    PASSWORD_RESET_URL: str = "http://localhost:8001/reset-password"
    YANDEX_CLIENT_ID: str = ""
    YANDEX_CLIENT_SECRET: str = ""
    YANDEX_REDIRECT_URI: str = "http://127.0.0.1:8001/yandex/callback/code"
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="forbid")

    @property
    def DB_URL(self):
        return URL.create(
            "postgresql+asyncpg",
            username=self.DB_USER,
            password=self.DB_PASS,
            host=self.DB_HOST,
            port=self.DB_PORT,
            database=self.DB_NAME,
        )


settings = Settings()
