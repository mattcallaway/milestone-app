"""Configuration management with safe defaults."""

import os
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with safe-by-default configuration."""

    # Safe-by-default: read-only mode unless explicitly enabled
    write_mode: bool = False

    # API settings
    api_host: str = "127.0.0.1"
    api_port: int = 8000

    # Logging
    log_level: str = "info"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


def is_write_enabled() -> bool:
    """Check if write mode is enabled."""
    return get_settings().write_mode
