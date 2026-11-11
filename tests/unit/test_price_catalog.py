"""Pruebas unitarias del catálogo de precios por scraping (RF-23). No acceden a internet."""

import json
from pathlib import Path

import pytest

from app.services.price_catalog import CATALOG, PriceParseError, parse_vtex_product, product_url

FIXTURE = json.loads((Path(__file__).parents[1] / "fixtures" / "promart_cemento.json").read_text(encoding="utf-8"))


@pytest.mark.evidencia(
    id="BU-90",
    nombre="Lectura del precio de un producto de Promart",
    requisito="RF-23",
    objetivo="Verificar que se extraen nombre, precio, disponibilidad y enlace de la respuesta del catálogo VTEX de Promart.",
    entrada="Respuesta real recortada de /api/catalog_system/pub/products/search/cemento-portland-tipo-i-x42-5kg-sol/p",
    esperado="Cemento Sol Portland Tipo I 42.5 kg, S/ 30,90, disponible, enlace del producto",
)
def test_lectura_precio(evidencia):
    p = parse_vtex_product(FIXTURE)
    evidencia["obtenido"] = f"{p.product_name} | S/ {p.price} | disponible={p.available} | {p.url}"
    assert p.product_name == "Cemento Sol Portland Tipo I 42.5 kg"
    assert p.price == pytest.approx(30.9)
    assert p.available is True
    assert p.url == "https://www.promart.pe/cemento-portland-tipo-i-x42-5kg-sol/p"


@pytest.mark.evidencia(
    id="BU-91",
    nombre="Respuesta de la tienda sin producto o sin precio",
    requisito="RF-23 / EX-09",
    objetivo="Verificar que una respuesta vacía o sin precio se detecta como error en lugar de guardar un precio falso.",
    entrada="[], un producto con Price = 0 y un objeto que no es lista",
    esperado="PriceParseError en los tres casos",
)
def test_respuesta_invalida(evidencia):
    sin_precio = json.loads(json.dumps(FIXTURE))
    sin_precio[0]["items"][0]["sellers"][0]["commertialOffer"]["Price"] = 0
    errores = []
    for data in ([], sin_precio, {"x": 1}):
        with pytest.raises(PriceParseError) as e:
            parse_vtex_product(data)
        errores.append(str(e.value))
    evidencia["obtenido"] = " | ".join(errores)


@pytest.mark.evidencia(
    id="BU-92",
    nombre="Catálogo de materiales",
    requisito="RF-23",
    objetivo="Verificar que cada material del catálogo tiene clave única, unidad de venta y contenido, y su URL de consulta.",
    entrada="Catálogo definido en price_catalog.CATALOG",
    esperado="Claves únicas; contenido > 0; los materiales con tienda apuntan a la API pública de Promart por slug",
)
def test_catalogo(evidencia):
    claves = [c.key for c in CATALOG]
    con_tienda = [c for c in CATALOG if c.slug]
    evidencia["obtenido"] = f"{len(CATALOG)} materiales, {len(con_tienda)} con tienda: {claves}"
    assert len(claves) == len(set(claves))
    assert all(c.content > 0 for c in CATALOG)
    assert product_url("cemento-portland-tipo-i-x42-5kg-sol") == (
        "https://www.promart.pe/api/catalog_system/pub/products/search/cemento-portland-tipo-i-x42-5kg-sol/p"
    )
    assert {"cement_bag", "paint_gallon", "porcelain_box", "brick_kk18", "barbed_wire_roll"} <= set(claves)


@pytest.mark.evidencia(
    id="BU-96",
    nombre="Datos extraños de la tienda",
    requisito="RF-23",
    objetivo="Verificar que un nombre muy largo se recorta, un precio NaN o infinito se rechaza y un enlace no HTTPS no se guarda.",
    entrada="Nombre de 500 caracteres; Price = NaN e Infinity; enlace http://",
    esperado="Nombre de 200 caracteres; PriceParseError para NaN e Infinity; enlace vacío",
)
def test_datos_extranos(evidencia):
    largo = json.loads(json.dumps(FIXTURE))
    largo[0]["productName"] = "x" * 500
    largo[0]["link"] = "http://www.promart.pe/producto/p"
    p = parse_vtex_product(largo)
    for valor in (float("nan"), float("inf")):
        malo = json.loads(json.dumps(FIXTURE))
        malo[0]["items"][0]["sellers"][0]["commertialOffer"]["Price"] = valor
        with pytest.raises(PriceParseError):
            parse_vtex_product(malo)
    evidencia["obtenido"] = f"nombre={len(p.product_name)} caracteres, enlace='{p.url}'"
    assert len(p.product_name) == 200
    assert p.url == ""
