"""Pruebas unitarias del metrado de acabados de un ambiente (CU-07, RF-22)."""

import pytest

from app.services.finishes import FinishParams, Opening, finishes_takeoff
from app.services.geometry import GeometryError

AULA = {"area_m2": 20.0, "walls": [5.0, 4.0, 5.0, 4.0]}  # 5 × 4 m
PUERTA = Opening(wall=0, kind="door", width_m=0.9, height_m=2.1)
VENTANA = Opening(wall=2, kind="window", width_m=1.2, height_m=1.0)


def _q(items, key):
    return next(i for i in items if i.key == key).quantity


@pytest.mark.evidencia(
    id="BU-93",
    nombre="Metrado de acabados de un ambiente",
    requisito="RF-22",
    objetivo="Verificar partidas e insumos con las reglas de obra: descuento de vanos, derrames, tarrajeo 1:5, 2 manos de látex.",
    entrada="Aula 5×4 m, altura 2,50 m, puerta 0,90×2,10 y ventana 1,20×1,00, muro de 0,15 m",
    esperado=("Tarrajeo 45 − 3,09 + 1,425 = 43,34 m²; contrazócalo 17,1 m; 16 cajas de porcelanato; 6 bolsas de pegamento; "
              "8 kg de fragua; 6 bolsas de cemento; 30 sacos de arena fina; 4 galones de látex; 1 imprimante de 4 gal"),
)
def test_metrado_acabados(evidencia):
    items = finishes_takeoff(AULA["area_m2"], AULA["walls"], FinishParams(height_m=2.5), [PUERTA, VENTANA]).items
    claves = ("floor_m2", "baseboard_m", "plaster_m2", "wall_paint_m2", "ceiling_paint_m2", "porcelain_box",
              "tile_adhesive_bag", "grout_kg", "cement_bag", "fine_sand_bag", "paint_gallon", "primer_4gal")
    obtenido = {k: _q(items, k) for k in claves}
    evidencia["obtenido"] = str(obtenido)
    assert obtenido["floor_m2"] == pytest.approx(20.0)
    assert obtenido["ceiling_paint_m2"] == pytest.approx(20.0)
    assert obtenido["baseboard_m"] == pytest.approx(17.1)
    assert obtenido["plaster_m2"] == pytest.approx(43.34, abs=0.01)
    assert obtenido["wall_paint_m2"] == pytest.approx(obtenido["plaster_m2"])
    assert (obtenido["porcelain_box"], obtenido["tile_adhesive_bag"], obtenido["grout_kg"]) == (16, 6, 8)
    assert (obtenido["cement_bag"], obtenido["fine_sand_bag"]) == (6, 30)
    assert (obtenido["paint_gallon"], obtenido["primer_4gal"]) == (4, 1)


@pytest.mark.evidencia(
    id="BU-94",
    nombre="Vano pequeño no se descuenta",
    requisito="RF-22",
    objetivo="Verificar que un vano de 0,25 m² o menos no se descuenta del tarrajeo ni suma derrames (Norma Técnica de Metrados).",
    entrada="Aula 5×4 m, altura 2,50 m, con una ventanilla de 0,40×0,40 m",
    esperado="Tarrajeo = 45 m² (área bruta)",
)
def test_vano_pequeno(evidencia):
    items = finishes_takeoff(20.0, AULA["walls"], FinishParams(height_m=2.5), [Opening(1, "window", 0.4, 0.4)]).items
    evidencia["obtenido"] = f"tarrajeo={_q(items, 'plaster_m2')} m²"
    assert _q(items, "plaster_m2") == pytest.approx(45.0)


@pytest.mark.evidencia(
    id="BU-95",
    nombre="Vanos inválidos",
    requisito="RF-22 / EX-08",
    objetivo="Verificar que se rechaza un vano en un muro inexistente, más ancho que su muro o más alto que el ambiente.",
    entrada="Vano en el muro 9; puerta de 6 m en muro de 5 m; puerta de 3 m de alto con altura 2,50 m",
    esperado="GeometryError en los tres casos",
)
def test_vanos_invalidos(evidencia):
    malos = [Opening(8, "door", 0.9, 2.1), Opening(0, "door", 6.0, 2.1), Opening(0, "door", 0.9, 3.0)]
    mensajes = []
    for vano in malos:
        with pytest.raises(GeometryError) as e:
            finishes_takeoff(20.0, AULA["walls"], FinishParams(height_m=2.5), [vano])
        mensajes.append(str(e.value))
    evidencia["obtenido"] = " | ".join(mensajes)
