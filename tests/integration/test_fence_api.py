"""Pruebas de integración: metrado y presupuesto de cerco perimétrico (CU-09, RF-24, RF-27)."""

import copy
import json
from pathlib import Path

import pytest

from app.services.price_catalog import refresh_prices
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


FIXTURE = json.loads((Path(__file__).parents[1] / "fixtures" / "promart_cemento.json").read_text(encoding="utf-8"))


def _store(url: str):
    data = copy.deepcopy(FIXTURE)
    data[0]["items"][0]["sellers"][0]["commertialOffer"]["Price"] = 8.0
    return data


@pytest.mark.evidencia(
    id="BI-53",
    nombre="Cerco de alambre presupuestado con el catálogo de la tienda",
    requisito="RF-23 / RF-24 / RF-27",
    objetivo=(
        "Verificar que, sin escribir precios, el cerco de alambre se presupuesta con el catálogo (poste de pino, "
        "rollo de púas y grapas de Promart) y que un precio escrito por el usuario reemplaza al de la tienda."
    ),
    precondiciones="Usuario autenticado con un terreno medido; catálogo actualizado (todos los productos a S/ 8)",
    entrada="Cerco de alambre sin precios; luego con posts_total = 25",
    esperado=(
        "Presupuesto con postes y pies de amigo a S/ 8, rollo a S/ 8, grapa a S/ 8 / (0,5 kg × 170 und/kg); "
        "origen «store»; con el precio escrito, postes a S/ 25 y origen «input»"
    ),
)
async def test_cerco_con_catalogo(auth_client, project, api, db_session, evidencia):
    await refresh_prices(db_session, _store, delay_s=0)
    sid = await _terreno(auth_client, project, api)
    body = (await auth_client.post(f"{api}/surveys/{sid}/fence", json={"kind": "wire"})).json()
    lines = {line["key"]: line["unit_price"] for line in body["budget"]["lines"]}
    own = (await auth_client.post(f"{api}/surveys/{sid}/fence", json={"kind": "wire", "prices": {"posts_total": 25}})).json()
    own_lines = {line["key"]: line["unit_price"] for line in own["budget"]["lines"]}
    evidencia["obtenido"] = (
        f"catálogo: {lines}, origen={body['price_sources']}; con precio propio: postes={own_lines['posts_total']}, "
        f"origen={own['price_sources']['posts_total']}"
    )
    assert lines["posts_total"] == lines["braces"] == lines["wire_rolls"] == 8.0
    assert lines["staples"] == pytest.approx(8.0 / (0.5 * 170), abs=0.005)
    assert body["price_sources"]["posts_total"] == "store"
    assert own_lines["posts_total"] == 25 and own_lines["braces"] == 8.0
    assert own["price_sources"]["posts_total"] == "input"


@pytest.mark.evidencia(
    id="BI-54",
    nombre="Cerco de ladrillo presupuestado con los materiales de la tienda",
    requisito="RF-23 / RF-24 / RF-27",
    objetivo=(
        "Verificar que el muro, los concretos, el cimiento, el sobrecimiento y el acero del cerco de ladrillo se "
        "presupuestan con los materiales del catálogo (ladrillo, cemento, arena, piedra y fierro de Promart)."
    ),
    precondiciones="Usuario autenticado con un terreno medido; catálogo actualizado (todos los productos a S/ 8)",
    entrada="Cerco de ladrillo de 2,40 m sin precios escritos",
    esperado=(
        "Muro = 39 × 1,05 ladrillos + 0,025 m³ de mortero 1:4 por m²; concretos, cimiento, sobrecimiento y acero "
        "con precio de la tienda; el trabajo (trazo, excavación, eliminación, encofrado) no entra al presupuesto"
    ),
)
async def test_cerco_ladrillo_con_catalogo(auth_client, project, api, db_session, evidencia):
    await refresh_prices(db_session, _store, delay_s=0)
    sid = await _terreno(auth_client, project, api)
    body = (await auth_client.post(f"{api}/surveys/{sid}/fence", json={"kind": "brick"})).json()
    lines = {line["key"]: line["unit_price"] for line in body["budget"]["lines"]}
    evidencia["obtenido"] = f"precios={lines}, sin precio={body['budget']['missing_prices']}"
    mortar = 0.025 * (8.9 * 42.5 * 8 / 42.5 + 1600 * 8 / 40)  # cemento + arena gruesa del mortero 1:4
    assert lines["wall_m2"] == pytest.approx(39 * 1.05 * 8 + mortar, abs=0.01)
    assert {"columns_concrete_m3", "beam_concrete_m3", "footing_m3", "plinth_m3", "steel_kg"} <= set(lines)
    trabajo = {"layout_m", "excavation_m3", "disposal_m3", "formwork_m2"}
    items = {i["key"]: i for i in body["items"]}
    assert all(not items[k]["priceable"] for k in trabajo)
    assert not trabajo & (set(lines) | set(body["budget"]["missing_prices"]))
    assert body["price_sources"]["wall_m2"] == "store"


@pytest.mark.evidencia(
    id="BI-55",
    nombre="Cerco de alambre: presupuesto solo de materiales (con la mezcla de los hoyos)",
    requisito="RF-24 / RF-27",
    objetivo=(
        "Verificar que el presupuesto del cerco de alambre lleva solo materiales: el concreto ciclópeo de los hoyos "
        "se costea con cemento, arena y piedra; el trazo y la excavación son trabajo y quedan como desglose. Un "
        "precio enviado por una versión anterior de la app para una partida de trabajo se ignora."
    ),
    precondiciones="Usuario autenticado con un terreno medido; catálogo actualizado (todos los productos a S/ 8)",
    entrada="Cerco de alambre con prices = {excavation_m3: 50} (app anterior)",
    esperado="HTTP 200; concrete_m3 con precio de la tienda; layout_m y excavation_m3 informativas y fuera del presupuesto",
)
async def test_cerco_alambre_solo_materiales(auth_client, project, api, db_session, evidencia):
    await refresh_prices(db_session, _store, delay_s=0)
    sid = await _terreno(auth_client, project, api)
    resp = await auth_client.post(f"{api}/surveys/{sid}/fence", json={"kind": "wire", "prices": {"excavation_m3": 50}})
    body = resp.json()
    lines = {line["key"]: line["unit_price"] for line in body["budget"]["lines"]}
    items = {i["key"]: i for i in body["items"]}
    evidencia["obtenido"] = f"HTTP {resp.status_code}, precios={lines}, sin precio={body['budget']['missing_prices']}"
    assert resp.status_code == 200
    assert lines["concrete_m3"] > 0 and body["price_sources"]["concrete_m3"] == "store"
    assert not items["layout_m"]["priceable"] and not items["excavation_m3"]["priceable"]
    assert not {"layout_m", "excavation_m3"} & (set(lines) | set(body["budget"]["missing_prices"]))
