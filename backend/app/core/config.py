from functools import lru_cache
from typing import Literal
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-120b"
    openai_api_key: str | None = None
    openai_model: str = "gpt-6-luna"
    openai_use_responses_api: bool = True
    openai_reasoning_effort: Literal["none", "low", "medium", "high", "xhigh", "max"] = "low"
    openai_reasoning_summary: bool = True
    traducir_resumen_groq: bool = True
    llm_reduce_tools_enabled: bool = True
    llm_primary_provider: Literal["openai", "groq"] = "openai"
    llm_fallback_enabled: bool = True
    groq_tpm_budget: int = Field(default=8000, gt=0)
    groq_max_output_tokens: int = Field(default=1024, gt=0)
    google_drive_folder_id: str | None = None
    google_oauth_client_json: str | None = None
    google_oauth_client_file: str | None = None
    google_oauth_token_json: str | None = None
    google_oauth_token_file: str = "token_drive.json"
    google_service_account_json: str | None = None
    google_service_account_file: str | None = None

    # Base de datos PostgreSQL
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/flucito"

    sae_firebird_host: str = "firebird"
    sae_firebird_password: str | None = None

    # Autenticación JWT y usuarios iniciales
    auth_required: bool = False
    jwt_secret_key: str = "flucito-clave-secreta-desarrollo-cambiar-en-produccion-2026"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7  # 7 días
    admin_initial_username: str = "robert"
    admin_initial_password: str = "Interflu2026!"
    admin_initial_name: str = "Robert (Administrador)"
    operador_initial_username: str = "almacen"
    operador_initial_password: str = "Almacen2026!"
    operador_initial_name: str = "Operador de Almacén"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    """para evitar leer el .env en cada request"""
    return Settings()


settings = get_settings()
