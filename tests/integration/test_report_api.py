"""Pruebas de integración: informe técnico en PDF (CU-10, RF-28)."""

import pytest

from tests.helpers import TERRENO_100x60, simulate_stop_and_go

WINCHA = {
    "walls": [
        {"wall_index": 0, "readings_m": [5.00, 5.002]},
        {"wall_index": 1, "readings_m": [4.00, 4.001]},
        {"wall_index": 2, "readings_m": [5.00, 5.03]},
        {"wall_index": 3, "readings_m": [3.998, 4.00]},
    ],
}


@pytest.mark.evidencia(
    id="BI-38",
    nombre="GET /surveys/{id}/report.pdf de un terreno GPS",
    requisito="RF-28 / RF-21",
    objetivo="Verificar que la API entrega el informe en PDF de un terreno medido con esquinas fijadas.",
    precondiciones="Usuario autenticado con un proyecto y un recorrido exterior",
    entrada="Recorrido stop-and-go del terreno 100×60 m; GET /surveys/{id}/report.pdf",
    esperado="HTTP 200, application/pdf, descarga con nombre de archivo y PDF válido con el nombre del terreno",
)
async def test_informe_terreno_gps(auth_client, project, api, evidencia):
    creado = await auth_client.post(
        f"{api}/projects/{project['id']}/surveys",
        json={"name": "Terreno UPAO", "mode": "exterior", "gps_points": simulate_stop_and_go(TERRENO_100x60, seed=5)},
    )
    resp = await auth_client.get(f"{api}/surveys/{creado.json()['id']}/report.pdf")
    evidencia["obtenido"] = (
        f"HTTP {resp.status_code}, {resp.headers.get('content-type')}, "
        f"{resp.headers.get('content-disposition')}, {len(resp.content)} bytes"
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert "attachment" in resp.headers["content-disposition"]
    assert resp.content.startswith(b"%PDF")
    assert b"Terreno UPAO" in resp.content


@pytest.mark.evidencia(
    id="BI-39",
    nombre="Informe de un ambiente validado con wincha",
    requisito="RF-28 / RF-14",
    objetivo="Verificar que el informe incluye la validación cuando el recorrido tiene medidas de wincha.",
    precondiciones="Usuario autenticado con un proyecto",
    entrada="Aula 5×4 m (esquinas) + medidas de wincha de los 4 muros; GET /surveys/{id}/report.pdf",
    esperado="HTTP 200 y el PDF contiene la sección de validación con MAE",
)
async def test_informe_ambiente_validado(auth_client, project, api, evidencia):
    creado = await auth_client.post(
        f"{api}/projects/{project['id']}/surveys",
        json={"name": "Aula 201", "mode": "interior", "corners": [[0, 0], [5, 0], [5, 4], [0, 4]]},
    )
    sid = creado.json()["id"]
    await auth_client.put(f"{api}/surveys/{sid}/references", json=WINCHA)
    resp = await auth_client.get(f"{api}/surveys/{sid}/report.pdf")
    evidencia["obtenido"] = f"HTTP {resp.status_code}, {len(resp.content)} bytes, MAE en el PDF={b'MAE' in resp.content}"
    assert resp.status_code == 200
    assert b"MAE" in resp.content
    assert b"Sin validaci" not in resp.content


@pytest.mark.evidencia(
    id="BI-40",
    nombre="Informe de un recorrido ajeno o inexistente",
    requisito="RNF-07",
    objetivo="Verificar que no se puede descargar el informe de un recorrido que no es del usuario.",
    entrada="GET /surveys/9999/report.pdf",
    esperado="HTTP 404",
)
async def test_informe_inexistente(auth_client, api, evidencia):
    resp = await auth_client.get(f"{api}/surveys/9999/report.pdf")
    evidencia["obtenido"] = f"HTTP {resp.status_code}"
    assert resp.status_code == 404
