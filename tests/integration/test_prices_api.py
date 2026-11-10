"""Pruebas de integración: catálogo de precios (RF-23). La tienda se simula: no se accede a internet."""

import copy
import json
from pathlib import Path

import pytest

from app.services.price_catalog import refresh_prices

FIXTURE = json.loads((Path(__file__).parents[1] / "fixtures" / "promart_cemento.json").read_text(encoding="utf-8"))


def _store(price: float = 30.9, fail: set[str] | None = None):
    """Tienda simulada: devuelve el producto de la fixture con el precio indicado; falla para los slugs en `fail`."""
    def fetch(url: str):
        if fail and any(slug in url for slug in fail):
            raise ConnectionError("tienda no disponible")
        data = copy.deepcopy(FIXTURE)
        data[0]["items"][0]["sellers"][0]["commertialOffer"]["Price"] = price
        return data
    return fetch


@pytest.mark.evidencia(
    id="BI-45",
    nombre="Actualización del catálogo y consulta de precios",
    requisito="RF-23",
    objetivo="Verificar que el job guarda el precio de cada material con tienda, fuente y fecha, y que GET /prices lo devuelve.",
    precondiciones="Usuario autenticado; tienda simulada a S/ 30,90",
    entrada="refresh_prices(); GET /prices",
    esperado="Los materiales con tienda tienen precio 30,90, fuente Promart y fecha; los demás aparecen sin precio",
)
async def test_catalogo_actualizado(auth_client, api, db_session, evidencia):
    reporte = await refresh_prices(db_session, _store(30.9), delay_s=0)
    body = (await auth_client.get(f"{api}/prices")).json()
    cemento = next(p for p in body if p["key"] == "cement_bag")
    sin_tienda = [p for p in body if p["source"] == "none"]
    evidencia["obtenido"] = f"actualizados={reporte.updated}, cemento={cemento}, sin tienda={[p['key'] for p in sin_tienda]}"
    assert reporte.updated >= 5 and reporte.failed == 0
    assert cemento["price"] == pytest.approx(30.9)
    assert cemento["source"] == "store" and cemento["store"] == "Promart"
    assert cemento["fetched_at"] and cemento["url"].startswith("https://www.promart.pe/")
    assert all(p["price"] is None for p in sin_tienda)


@pytest.mark.evidencia(
    id="BI-46",
    nombre="Si la tienda falla se conserva el último precio",
    requisito="RF-23 / EX-09",
    objetivo="Verificar que un fallo de la tienda no borra el precio anterior y queda registrado el error.",
    precondiciones="Catálogo actualizado una vez a S/ 30,90",
    entrada="Segunda actualización a S/ 35,00 donde falla el cemento",
    esperado="Cemento sigue en 30,90 con su fecha anterior y estado 'error'; los demás pasan a 35,00",
)
async def test_fallo_conserva_precio(auth_client, api, db_session, evidencia):
    await refresh_prices(db_session, _store(30.9), delay_s=0)
    reporte = await refresh_prices(db_session, _store(35.0, fail={"cemento-portland"}), delay_s=0)
    body = {p["key"]: p for p in (await auth_client.get(f"{api}/prices")).json()}
    evidencia["obtenido"] = (
        f"fallidos={reporte.failed}, cemento={body['cement_bag']['price']} ({body['cement_bag']['status']}), "
        f"pintura={body['paint_gallon']['price']}"
    )
    assert reporte.failed == 1
    assert body["cement_bag"]["price"] == pytest.approx(30.9)
    assert body["cement_bag"]["status"] == "error"
    assert body["paint_gallon"]["price"] == pytest.approx(35.0)


@pytest.mark.evidencia(
    id="BI-47",
    nombre="Precio propio del usuario",
    requisito="RF-23",
    objetivo="Verificar que el usuario puede reemplazar el precio de un material y volver al de la tienda.",
    precondiciones="Catálogo actualizado a S/ 30,90",
    entrada="PUT /prices/cement_bag {price: 28.5}; DELETE /prices/cement_bag; PUT de clave inexistente y de precio negativo",
    esperado="28,50 con fuente 'user'; luego 30,90 con fuente 'store'; 404 y 422",
)
async def test_precio_usuario(auth_client, api, db_session, evidencia):
    await refresh_prices(db_session, _store(30.9), delay_s=0)
    put = await auth_client.put(f"{api}/prices/cement_bag", json={"price": 28.5})
    propio = next(p for p in (await auth_client.get(f"{api}/prices")).json() if p["key"] == "cement_bag")
    borrar = await auth_client.delete(f"{api}/prices/cement_bag")
    tienda = next(p for p in (await auth_client.get(f"{api}/prices")).json() if p["key"] == "cement_bag")
    r404 = await auth_client.put(f"{api}/prices/no_existe", json={"price": 1})
    r422 = await auth_client.put(f"{api}/prices/cement_bag", json={"price": -1})
    evidencia["obtenido"] = (
        f"PUT {put.status_code} → {propio['price']} ({propio['source']}); DELETE {borrar.status_code} → "
        f"{tienda['price']} ({tienda['source']}); {r404.status_code}, {r422.status_code}"
    )
    assert put.status_code == 200 and propio["price"] == pytest.approx(28.5) and propio["source"] == "user"
    assert propio["store_price"] == pytest.approx(30.9)
    assert borrar.status_code == 204 and tienda["source"] == "store"
    assert (r404.status_code, r422.status_code) == (404, 422)
