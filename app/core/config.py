"""Configuración de la aplicación cargada desde variables de entorno (.env)."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "MetriK API"
    app_version: str = "0.1.0"
    debug: bool = False
    api_prefix: str = "/api/v1"

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/metrik"

    @field_validator("database_url")
    @classmethod
    def _normalize_url(cls, v: str) -> str:
        return normalize_database_url(v)

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

    # Modelos de ML entrenados (.joblib) incluidos en el repositorio
    ml_models_dir: Path = Path(__file__).resolve().parents[2] / "ml" / "modelos"


def normalize_database_url(url: str) -> str:
    """Convierte la URL que entrega el proveedor (postgres://, postgresql://, ?sslmode=require)
    al formato del driver asíncrono asyncpg (postgresql+asyncpg://, ?ssl=require)."""
    u = url.strip()
    for prefix in ("postgres://", "postgresql://"):
        if u.startswith(prefix):
            u = "postgresql+asyncpg://" + u[len(prefix):]
            break
    if u.startswith("postgresql+asyncpg://") and "?" in u:
        base, query = u.split("?", 1)
        params = []
        for part in query.split("&"):
            key, _, value = part.partition("=")
            if key == "sslmode":
                params.append(f"ssl={'require' if value in ('require', 'verify-ca', 'verify-full', 'prefer') else value}")
            elif key in ("channel_binding", "options"):
                continue  # no soportados por asyncpg
            else:
                params.append(part)
        u = base + ("?" + "&".join(params) if params else "")
    return u


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
