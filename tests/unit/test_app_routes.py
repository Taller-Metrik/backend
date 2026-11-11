"""Pruebas del registro de routers de la API."""

from collections import Counter

import pytest
from app.main import create_app


@pytest.mark.evidencia(
    id="BU-104",
    nombre="Cada ruta de la API se registra una sola vez",
    requisito="RNF (mantenibilidad)",
    objetivo="Verificar que ningún router se incluye dos veces en la aplicación (rutas duplicadas en /docs y "
    "operation_id repetidos), un error típico al resolver conflictos en app/main.py.",
    entrada="Aplicación creada con create_app()",
    esperado="Ningún router aparece incluido más de una vez",
)
def test_rutas_sin_duplicados(evidencia):
    app = create_app(use_lifespan=False)
    # FastAPI ≥ 0.16x guarda cada include_router como un objeto con `original_router`
    incluidos = [r.original_router for r in app.routes if hasattr(r, "original_router")]
    veces = Counter(id(r) for r in incluidos)
    repetidos = sorted({(r.tags or ["?"])[0] for r in incluidos if veces[id(r)] > 1})
    evidencia["obtenido"] = f"routers incluidos={len(incluidos)}, repetidos={repetidos}"
    assert incluidos, "no se encontraron routers incluidos: revisar la versión de FastAPI"
    assert repetidos == []
