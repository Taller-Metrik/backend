"""Pruebas unitarias de la configuración de la base de datos."""

import pytest

from app.core.config import normalize_database_url
from app.core.database import engine_options


@pytest.mark.evidencia(
    id="BU-58",
    nombre="URL de la base de datos de producción",
    requisito="RNF-09",
    objetivo="Verificar que la URL del proveedor se adapta al driver asíncrono y que el pooler desactiva la caché de sentencias.",
    entrada="postgres://u:p@ep-x-pooler.neon.tech/db?sslmode=require&channel_binding=require y una URL sin pooler",
    esperado="postgresql+asyncpg://...?ssl=require; caché desactivada solo con pooler",
)
def test_url_produccion(evidencia):
    url = normalize_database_url("postgres://u:p@ep-x-pooler.neon.tech/db?sslmode=require&channel_binding=require")
    con_pooler = engine_options(url)
    sin_pooler = engine_options(normalize_database_url("postgresql://u:p@db.local:5432/db"))
    evidencia["obtenido"] = f"url={url.replace('u:p', 'u:***')}, pooler={con_pooler}, sin pooler={sin_pooler}"
    assert url == "postgresql+asyncpg://u:p@ep-x-pooler.neon.tech/db?ssl=require"
    assert con_pooler["connect_args"]["statement_cache_size"] == 0
    assert sin_pooler == {}
