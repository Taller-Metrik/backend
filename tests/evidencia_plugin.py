"""Plugin de pytest para registrar evidencias de cada prueba.

Uso en un test:

    @pytest.mark.evidencia(
        id="BU-01",
        nombre="Área de un rectángulo",
        requisito="RF-06",
        objetivo="...",
        entrada="...",
        esperado="...",
    )
    def test_algo(evidencia):
        resultado = ...
        evidencia["obtenido"] = resultado

Con `pytest --evidencias` se escribe `evidencias/_resultados/backend.json`, que
luego usa `scripts/generar_evidencias.py` para crear la captura (.png) y la
descripción (.txt) de cada prueba.
"""

import json
from datetime import datetime
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTADOS_DIR = REPO_ROOT / "evidencias" / "_resultados"

CAMPOS = ("id", "nombre", "requisito", "objetivo", "precondiciones", "entrada", "esperado")
_registros: dict[str, dict] = {}


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--evidencias", action="store_true", help="Registrar evidencias de las pruebas")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "evidencia(**campos): metadatos de evidencia de la prueba")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    ids: dict[str, str] = {}
    for item in items:
        marker = item.get_closest_marker("evidencia")
        if marker is None:
            continue
        test_id = marker.kwargs.get("id")
        if test_id in ids:
            raise pytest.UsageError(f"ID de evidencia duplicado {test_id}: {ids[test_id]} y {item.nodeid}")
        ids[test_id] = item.nodeid


@pytest.fixture
def evidencia(request: pytest.FixtureRequest):
    """Diccionario donde la prueba anota el resultado obtenido.

    Al terminar imprime el resumen; con `pytest -rA` aparece en la salida (y en la captura).
    """
    data: dict = {}
    request.node.evidencia_data = data
    yield data
    marker = request.node.get_closest_marker("evidencia")
    if marker is not None:
        print(f"[{marker.kwargs.get('id')}] {marker.kwargs.get('nombre')}")
        print(f"  Requisito : {marker.kwargs.get('requisito', '-')}")
        print(f"  Entrada   : {marker.kwargs.get('entrada', '-')}")
        print(f"  Esperado  : {marker.kwargs.get('esperado', '-')}")
        print(f"  Obtenido  : {data.get('obtenido', '-')}")


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    report = yield
    marker = item.get_closest_marker("evidencia")
    if marker is None or report.when not in ("setup", "call"):
        return report
    if report.when == "setup" and report.passed:
        return report

    datos = getattr(item, "evidencia_data", {})
    meta = {campo: marker.kwargs.get(campo, "") for campo in CAMPOS}
    meta.update(
        {
            "nodeid": item.nodeid,
            "estado": "APROBADO" if report.passed else "FALLIDO",
            "obtenido": str(datos.get("obtenido", "")),
            "duracion_s": round(report.duration, 4),
            "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    )
    if report.failed:
        meta["detalle_error"] = str(report.longrepr)[-2000:]
    _registros[meta["id"]] = meta
    return report


def pytest_sessionfinish(session: pytest.Session) -> None:
    if not session.config.getoption("--evidencias") or not _registros:
        return
    RESULTADOS_DIR.mkdir(parents=True, exist_ok=True)
    salida = RESULTADOS_DIR / "backend.json"
    existentes: dict[str, dict] = {}
    if salida.exists():
        existentes = {r["id"]: r for r in json.loads(salida.read_text(encoding="utf-8"))}
    existentes.update(_registros)
    ordenados = sorted(existentes.values(), key=lambda r: r["id"])
    salida.write_text(json.dumps(ordenados, ensure_ascii=False, indent=2), encoding="utf-8")
