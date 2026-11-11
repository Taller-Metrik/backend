"""Pruebas de integración: metrado de acabados con presupuesto (CU-07, RF-22, RF-24)."""

import copy
import json
from pathlib import Path

import pytest

from app.services.price_catalog import refresh_prices
from tests.helpers import TERRENO_100x60, simulate_stop_and_go

FIXTURE = json.loads((Path(__file__).parents[1] / "fixtures" / "promart_cemento.json").read_text(encoding="utf-8"))
VANOS = [
    {"wall": 0, "kind": "door", "width_m": 0.9, "height_m": 2.1},
    {"wall": 2, "kind": "window", "width_m": 1.2, "height_m": 1.0},
]


def _store(url: str):
    data = copy.deepcopy(FIXTURE)
    data[0]["items"][0]["sellers"][0]["commertialOffer"]["Price"] = 30.9
    return data


async def _recorrido(auth_client, project, api, mode="interior") -> int:
    if mode == "exterior":
        body = {"name": "Terreno", "mode": "exterior", "gps_points": simulate_stop_and_go(TERRENO_100x60, seed=1)}
    else:
        body = {"name": "Aula 201", "mode": "interior", "corners": [[0, 0], [5, 0], [5, 4], [0, 4]]}
    resp = await auth_client.post(f"{api}/projects/{project['id']}/surveys", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.mark.evidencia(
    id="BI-48",
    nombre="POST /surveys/{id}/finishes con precios del catálogo y mano de obra",
    requisito="RF-22 / RF-23 / RF-24",
    objetivo="Verificar que el metrado usa los precios de la tienda para los insumos y los del usuario para la mano de obra.",
    precondiciones="Catálogo actualizado (tienda simulada a S/ 30,90); usuario con su precio propio de cemento S/ 28,00",
    entrada="Aula 5×4 m, altura 2,50 m, puerta y ventana; mano de obra de piso S/ 25 por m²",
    esperado="HTTP 200; porcelanato a S/ 30,90 (tienda), cemento a S/ 28,00 (usuario), piso 20 m² × S/ 25; pegamento sin precio",
)
async def test_acabados_con_presupuesto(auth_client, project, api, db_session, evidencia):
    await refresh_prices(db_session, _store, delay_s=0)
    await auth_client.put(f"{api}/prices/cement_bag", json={"price": 28.0})
    sid = await _recorrido(auth_client, project, api)
    resp = await auth_client.post(
        f"{api}/surveys/{sid}/finishes",
        json={"height_m": 2.5, "openings": VANOS, "labor_prices": {"floor_m2": 25}},
    )
    body = resp.json()
    lineas = {line["key"]: line for line in body["budget"]["lines"]}
    evidencia["obtenido"] = (
        f"HTTP {resp.status_code}; porcelanato={lineas['porcelain_box']['unit_price']} "
        f"({body['price_sources']['porcelain_box']}); cemento={lineas['cement_bag']['unit_price']} "
        f"({body['price_sources']['cement_bag']}); piso={lineas['floor_m2']['subtotal']}; total={body['budget']['total']}"
    )
    assert resp.status_code == 200
    assert lineas["porcelain_box"]["unit_price"] == pytest.approx(30.9)
    assert body["price_sources"]["porcelain_box"] == "store"
    assert lineas["cement_bag"]["unit_price"] == pytest.approx(28.0)
    assert body["price_sources"]["cement_bag"] == "user"
    assert lineas["floor_m2"]["subtotal"] == pytest.approx(500.0)
    assert "tile_adhesive_bag" in body["budget"]["missing_prices"]
    assert body["assumptions"]


@pytest.mark.evidencia(
    id="BI-49",
    nombre="Acabados de un terreno o de un recorrido ajeno",
    requisito="RF-22 / RNF-07",
    objetivo="Verificar que el metrado de acabados solo aplica a ambientes interiores del usuario.",
    entrada="Terreno exterior; recorrido 9999; altura de 9 m",
    esperado="HTTP 422, 404 y 422",
)
async def test_acabados_errores(auth_client, project, api, evidencia):
    terreno = await _recorrido(auth_client, project, api, mode="exterior")
    aula = await _recorrido(auth_client, project, api)
    r1 = await auth_client.post(f"{api}/surveys/{terreno}/finishes", json={"height_m": 2.5})
    r2 = await auth_client.post(f"{api}/surveys/9999/finishes", json={"height_m": 2.5})
    r3 = await auth_client.post(f"{api}/surveys/{aula}/finishes", json={"height_m": 9})
    evidencia["obtenido"] = f"{r1.status_code}, {r2.status_code}, {r3.status_code}"
    assert (r1.status_code, r2.status_code, r3.status_code) == (422, 404, 422)
