"""Pruebas de integración: metrado y presupuesto de cerco perimétrico (CU-09, RF-24, RF-27)."""

import pytest

from tests.helpers import TERRENO_100x60, simulate_stop_and_go


async def _terreno(auth_client, project, api) -> int:
    resp = await auth_client.post(
        f"{api}/projects/{project['id']}/surveys",
        json={"name": "Fundo", "mode": "exterior", "gps_points": simulate_stop_and_go(TERRENO_100x60, dwell_s=60, seed=4)},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.mark.evidencia(
    id="BI-42",
    nombre="POST /surveys/{id}/fence: cerco de alambre con presupuesto",
    requisito="RF-27 / RF-24",
    objetivo="Verificar el metrado del cerco de un terreno medido con GPS, con rango de compra y presupuesto.",
    precondiciones="Usuario autenticado con un terreno medido con esquinas fijadas",
    entrada="Cerco de alambre con un portón de 4 m; precios de postes, rollos y portón; GG 10 %, utilidad 5 %",
    esperado="HTTP 200, U95 del perímetro usado, postes mín < máx, presupuesto con IGV y advertencia de metrado referencial",
)
async def test_cerco_alambre_api(auth_client, project, api, evidencia):
    sid = await _terreno(auth_client, project, api)
    resp = await auth_client.post(
        f"{api}/surveys/{sid}/fence",
        json={
            "kind": "wire",
            "gates": [{"side": 0, "width_m": 4}],
            "prices": {"posts_total": 25, "wire_rolls": 120, "gates": 600},
            "overhead_pct": 10, "profit_pct": 5,
        },
    )
    body = resp.json()
    postes = next(i for i in body["items"] if i["key"] == "posts_total")
    evidencia["obtenido"] = (
        f"HTTP {resp.status_code}, P={body['perimeter_m']:.1f} ± {body['perimeter_u95_m']:.1f} m, "
        f"postes {postes['min']}–{postes['max']} (comprar {postes['purchase']}), total S/ {body['budget']['total']:.2f}"
    )
    assert resp.status_code == 200
    assert body["perimeter_u95_m"] > 0
    assert postes["min"] < postes["max"] == postes["purchase"]
    assert body["budget"]["total"] > body["budget"]["direct_cost"] > 0
    assert "staples" in body["budget"]["missing_prices"]
    assert any("referencial" in n for n in body["notes"])


@pytest.mark.evidencia(
    id="BI-43",
    nombre="Cerco de ladrillo sin presupuesto",
    requisito="RF-27",
    objetivo="Verificar el metrado de un muro de albañilería y que sin precios no se arma presupuesto.",
    precondiciones="Usuario autenticado con un terreno medido",
    entrada="Cerco de ladrillo de 2,40 m sin portones ni precios",
    esperado="HTTP 200, partidas de columnas, muro y ladrillos; budget = null; supuestos listados",
)
async def test_cerco_ladrillo_api(auth_client, project, api, evidencia):
    sid = await _terreno(auth_client, project, api)
    resp = await auth_client.post(f"{api}/surveys/{sid}/fence", json={"kind": "brick"})
    body = resp.json()
    claves = {i["key"] for i in body["items"]}
    evidencia["obtenido"] = f"HTTP {resp.status_code}, partidas={sorted(claves)}, budget={body['budget']}"
    assert resp.status_code == 200
    assert {"columns", "wall_m2", "bricks"} <= claves
    assert body["budget"] is None
    assert body["assumptions"]


@pytest.mark.evidencia(
    id="BI-44",
    nombre="Cerco con datos inválidos o de un recorrido ajeno",
    requisito="RF-27 / RNF-07",
    objetivo="Verificar las respuestas de error del endpoint de cerco.",
    entrada="Portón en el lado 9; precio negativo; recorrido 9999",
    esperado="HTTP 422, 422 y 404",
)
async def test_cerco_errores(auth_client, project, api, evidencia):
    sid = await _terreno(auth_client, project, api)
    r1 = await auth_client.post(f"{api}/surveys/{sid}/fence", json={"kind": "wire", "gates": [{"side": 9, "width_m": 3}]})
    r2 = await auth_client.post(f"{api}/surveys/{sid}/fence", json={"kind": "wire", "prices": {"posts_total": -1}})
    r3 = await auth_client.post(f"{api}/surveys/9999/fence", json={"kind": "wire"})
    evidencia["obtenido"] = f"{r1.status_code}, {r2.status_code}, {r3.status_code}"
    assert (r1.status_code, r2.status_code, r3.status_code) == (422, 422, 404)
