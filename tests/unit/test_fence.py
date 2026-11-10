"""Pruebas unitarias del metrado de cerco perimétrico y del presupuesto (CU-09, RF-24, RF-27)."""

import pytest

from app.services.budget import build_budget
from app.services.fence import FenceParams, Gate, TakeoffItem, fence_takeoff
from app.services.geometry import GeometryError

TERRENO = [100.0, 60.0, 100.0, 60.0]  # lados del terreno 100×60 m


def _item(takeoff, key):
    return next(i for i in takeoff.items if i.key == key)


@pytest.mark.evidencia(
    id="BU-80",
    nombre="Metrado de cerco de alambre de púas",
    requisito="RF-27",
    objetivo="Verificar postes, pies de amigo, alambre en rollos y grapas con las reglas de obra (postes cada 3 m, refuerzo cada 50 m).",
    entrada="Terreno 100×60 m, 4 esquinas, sin portones, 4 hilos, sin incertidumbre",
    esperado="100 postes de línea + 4 de refuerzo + 4 esquineros = 108; 16 pies de amigo; 1344 m de alambre = 7 rollos; 476 grapas",
)
def test_cerco_alambre(evidencia):
    t = fence_takeoff(TERRENO, FenceParams(kind="wire"))
    claves = ("posts_line", "posts_brace", "posts_corner", "posts_total", "braces", "wire_m", "wire_rolls", "staples")
    resumen = {k: _item(t, k).quantity for k in claves}
    evidencia["obtenido"] = str(resumen)
    assert resumen["posts_line"] == 100
    assert resumen["posts_brace"] == 4
    assert resumen["posts_corner"] == 4
    assert resumen["posts_total"] == 108
    assert resumen["braces"] == 16
    assert resumen["wire_m"] == pytest.approx(1344)
    assert resumen["wire_rolls"] == 7
    assert resumen["staples"] == 476


@pytest.mark.evidencia(
    id="BU-81",
    nombre="Portón en el cerco de alambre",
    requisito="RF-27",
    objetivo="Verificar que el portón descuenta su ancho, agrega 2 postes reforzados y divide el lado en dos tramos.",
    entrada="Terreno 100×60 m con un portón de 4 m en el lado 1",
    esperado="2 postes de portón, 1 portón, alambre (320 − 4) × 4 × 1,05 = 1327,2 m y el lado 1 sin poste de refuerzo (tramos de 48 m)",
)
def test_porton_alambre(evidencia):
    t = fence_takeoff(TERRENO, FenceParams(kind="wire"), gates=[Gate(side=0, width_m=4.0)])
    evidencia["obtenido"] = (
        f"postes portón={_item(t, 'posts_gate').quantity}, portones={_item(t, 'gates').quantity}, "
        f"alambre={_item(t, 'wire_m').quantity} m, refuerzos={_item(t, 'posts_brace').quantity}"
    )
    assert _item(t, "posts_gate").quantity == 2
    assert _item(t, "gates").quantity == 1
    assert _item(t, "wire_m").quantity == pytest.approx(1327.2)
    assert _item(t, "posts_brace").quantity == 3  # el lado con portón queda en tramos de 48 m
    assert t.net_length_m == pytest.approx(316)


@pytest.mark.evidencia(
    id="BU-82",
    nombre="Metrado de muro de ladrillo",
    requisito="RF-27",
    objetivo="Verificar columnas, muro, ladrillos, mortero y concreto de un cerco de albañilería.",
    entrada="Terreno 10×10 m, altura 2,40 m, columnas cada 3 m, sin portones",
    esperado="16 columnas; muro (40 − 16×0,25) × 2,20 = 79,2 m²; 3244 ladrillos; cimiento 11,2 m³; eliminación 14 m³",
)
def test_muro_ladrillo(evidencia):
    t = fence_takeoff([10.0, 10.0, 10.0, 10.0], FenceParams(kind="brick"))
    evidencia["obtenido"] = (
        f"columnas={_item(t, 'columns').quantity}, muro={_item(t, 'wall_m2').quantity} m², "
        f"ladrillos={_item(t, 'bricks').quantity}, cimiento={_item(t, 'footing_m3').quantity} m³"
    )
    assert _item(t, "columns").quantity == 16
    assert _item(t, "wall_m2").quantity == pytest.approx(79.2)
    assert _item(t, "bricks").quantity == 3244
    assert _item(t, "footing_m3").quantity == pytest.approx(11.2)
    assert _item(t, "disposal_m3").quantity == pytest.approx(14.0)


@pytest.mark.evidencia(
    id="BU-83",
    nombre="Rango de compra según la incertidumbre del perímetro",
    requisito="RF-27 / RF-21",
    objetivo="Verificar que la incertidumbre del perímetro se convierte en un rango mín–máx y que se recomienda comprar el máximo.",
    entrada="Terreno 100×60 m (P = 320 m) con U95 del perímetro = 9,6 m (3 %)",
    esperado="postes mín < nominal < máx, rollos a comprar = rollos máx y advertencia con ±9,6 m",
)
def test_rango_de_compra(evidencia):
    t = fence_takeoff(TERRENO, FenceParams(kind="wire"), perimeter_u95_m=9.6)
    postes, rollos = _item(t, "posts_total"), _item(t, "wire_rolls")
    evidencia["obtenido"] = (
        f"postes {postes.min}–{postes.quantity}–{postes.max}, comprar={postes.purchase}; rollos comprar={rollos.purchase}"
    )
    assert postes.min < postes.quantity < postes.max
    assert postes.purchase == postes.max
    assert rollos.purchase == rollos.max
    assert any("9,6 m" in n for n in t.notes)


@pytest.mark.evidencia(
    id="BU-84",
    nombre="Portón inválido",
    requisito="RF-27",
    objetivo="Verificar que se rechaza un portón en un lado inexistente o más ancho que su lado.",
    entrada="Portón en el lado 8 de un terreno de 4 lados; portón de 70 m en un lado de 60 m",
    esperado="GeometryError en ambos casos",
)
def test_porton_invalido(evidencia):
    with pytest.raises(GeometryError) as e1:
        fence_takeoff(TERRENO, FenceParams(kind="wire"), gates=[Gate(side=7, width_m=3.0)])
    with pytest.raises(GeometryError) as e2:
        fence_takeoff(TERRENO, FenceParams(kind="wire"), gates=[Gate(side=1, width_m=70.0)])
    evidencia["obtenido"] = f"{e1.value} | {e2.value}"


@pytest.mark.evidencia(
    id="BU-85",
    nombre="Presupuesto con gastos generales, utilidad e IGV",
    requisito="RF-24",
    objetivo="Verificar el cálculo del presupuesto: costo directo, gastos generales, utilidad, IGV y partidas sin precio.",
    entrada="128 postes × S/ 25, 7 rollos × S/ 120 y 316 m de mano de obra × S/ 8 (grapas sin precio); GG 10 %, utilidad 5 %, IGV 18 %",
    esperado="Costo directo S/ 6568,00; GG 656,80; utilidad 328,40; subtotal 7553,20; IGV 1359,58; total 8912,78; grapas sin precio",
)
def test_presupuesto(evidencia):
    items = [
        TakeoffItem("posts_total", "Postes", "und", 128, 128, 128, 128),
        TakeoffItem("wire_rolls", "Rollos de alambre", "rollo", 7, 7, 7, 7),
        TakeoffItem("labor_m", "Mano de obra", "m", 316, 316, 316, 316),
        TakeoffItem("staples", "Grapas", "und", 500, 500, 500, 500),
    ]
    b = build_budget(items, {"posts_total": 25, "wire_rolls": 120, "labor_m": 8}, overhead_pct=10, profit_pct=5, igv_pct=18)
    evidencia["obtenido"] = (
        f"CD={b.direct_cost:.2f}, GG={b.overhead:.2f}, U={b.profit:.2f}, ST={b.subtotal:.2f}, "
        f"IGV={b.igv:.2f}, total={b.total:.2f}, sin precio={b.missing_prices}"
    )
    assert b.direct_cost == pytest.approx(6568.00)
    assert b.overhead == pytest.approx(656.80)
    assert b.profit == pytest.approx(328.40)
    assert b.subtotal == pytest.approx(7553.20)
    assert b.igv == pytest.approx(1359.58)
    assert b.total == pytest.approx(8912.78)
    assert b.missing_prices == ["staples"]
