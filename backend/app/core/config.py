from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "sqlite:///./vrmmo.db"

    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "hermes3:8b-llama3.1-q4_K_M"
    ollama_timeout_seconds: float = 180.0

    log_level: str = "INFO"

    cors_origins: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
