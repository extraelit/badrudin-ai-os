"""Конфигурация backend через переменные окружения (Pydantic settings).

Значения читаются из окружения / файла .env (D-008; ARCHITECTURE.md раздел 12.3).
Секреты в код не помещаются; в репозитории — только .env.example (T-1.A2).
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки приложения, считываемые из окружения."""

    app_name: str = "Badrudin AI OS"
    app_env: str = "development"  # development | test | staging | production
    app_debug: bool = True

    backend_host: str = "0.0.0.0"
    backend_port: int = 8000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # прочие переменные окружения (БД, Redis и т. д.) игнорируются здесь
    )


@lru_cache
def get_settings() -> Settings:
    """Возвращает кэшированный экземпляр настроек."""
    return Settings()
