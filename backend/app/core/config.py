from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    groq_api_key: str
    groq_model: str = "llama-3.3-70b-versatile"
    google_drive_folder_id: str | None = None
    google_oauth_client_json: str | None = None
    google_oauth_client_file: str | None = None
    google_oauth_token_json: str | None = None
    google_oauth_token_file: str = "token_drive.json"
    google_service_account_json: str | None = None
    google_service_account_file: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    """para evitar leer el .env en cada request"""
    return Settings()


settings = get_settings()
