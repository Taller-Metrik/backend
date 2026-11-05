"""Configuración de la aplicación cargada desde variables de entorno (.env)."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "MetriK API"
    app_version: str = "0.1.0"
    debug: bool = False
    api_prefix: str = "/api/v1"

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/metrik"

    secret_key: str = Field(default="cambiar-en-produccion-clave-de-al-menos-32-caracteres", min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24

    allowed_origins: list[str] = ["*"]

    # Parámetros de cálculo (ver docs/03-algoritmos.md)
    rdp_epsilon_m: float = 0.10
    snap_tolerance_deg: float = 15.0
    closure_tolerance_m: float = 1.0
    gps_max_accuracy_m: float = 10.0
    gps_calibration_threshold_m: float = 8.0


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
