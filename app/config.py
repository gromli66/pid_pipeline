"""
Application Configuration - загрузка настроек из .env
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional
from functools import lru_cache


class Settings(BaseSettings):
    """Настройки приложения."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",  # Игнорировать лишние переменные в .env
    )
    
    # Database
    DATABASE_URL: str = Field(
        default="postgresql://pid_user:changeme@localhost:5433/pid_pipeline"
    )
    
    # Redis / Celery
    CELERY_BROKER_URL: str = Field(default="redis://localhost:6380/0")
    CELERY_RESULT_BACKEND: str = Field(default="redis://localhost:6380/0")
    CELERY_TASK_TIME_LIMIT: int = Field(default=3600)
    
    # CVAT
    CVAT_URL: str = Field(default="http://localhost:8080")
    CVAT_TOKEN: Optional[str] = Field(default=None)
    
    # Storage
    STORAGE_PATH: str = Field(default="./storage/diagrams")
    
    # Projects
    PROJECTS_CONFIG_DIR: str = Field(default="./configs/projects")
    
    # API
    API_HOST: str = Field(default="0.0.0.0")
    API_PORT: int = Field(default=8000)
    DEBUG: bool = Field(default=False)
    
    # Logging
    LOG_LEVEL: str = Field(default="INFO")


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
