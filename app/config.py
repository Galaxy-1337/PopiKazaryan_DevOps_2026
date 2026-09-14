"""Конфигурация приложения.

Все параметры читаются из переменных окружения (файл ``.env`` при локальном
запуске). Секреты в коде не хранятся — только безопасные значения по умолчанию,
пригодные исключительно для локальной разработки.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки приложения, собираемые из переменных окружения."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Приложение ---------------------------------------------------
    app_name: str = Field(default="Конференция")
    app_env: str = Field(default="local")
    app_debug: bool = Field(default=True)
    app_host: str = Field(default="127.0.0.1")
    app_port: int = Field(default=8000)

    # --- База данных ---------------------------------------------------
    database_url: str = Field(default="sqlite+pysqlite:///./data/conference.db")

    # --- Администратор -------------------------------------------------
    admin_email: str = Field(default="admin@conference.local")
    admin_password: str = Field(default="ChangeMe_12345")
    admin_full_name: str = Field(default="Администратор программы")

    # --- Демонстрационные данные ---------------------------------------
    seed_demo_data: bool = Field(default=True)

    # --- Правила предметной области ------------------------------------
    section_capacity: int = Field(default=3, ge=1)
    hotel_confirmation_hours: int = Field(default=48, ge=1)
    abstract_max_size_kb: int = Field(default=512, ge=1)

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def safe_database_url(self) -> str:
        """URL базы данных без пароля — для логов и служебных ответов."""
        url = self.database_url
        if "@" not in url or "://" not in url:
            return url
        scheme, rest = url.split("://", 1)
        creds, host = rest.split("@", 1)
        user = creds.split(":", 1)[0]
        return f"{scheme}://{user}:***@{host}"


@lru_cache
def get_settings() -> Settings:
    """Вернуть singleton-настройки приложения."""
    return Settings()
