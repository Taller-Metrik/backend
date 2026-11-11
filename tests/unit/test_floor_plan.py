"""Pruebas unitarias del plano de vivienda con varios ambientes (CU-08, RF-25, RF-26)."""

import math

import pytest

from app.services.floor_plan import Join, Room, build_floor_plan, floor_plan_dxf
from app.services.geometry import GeometryError


def _rect(w: float, h: float) -> list[tuple[float, float]]:
    return [(0.0, 0.0), (w, 0.0), (w, h), (0.0, h)]


def _rot(pts, deg):
    a = math.radians(deg)
    return [(x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)) for x, y in pts]


SALA = Room(1, "Sala", _rect(4, 3))
COCINA = Room(2, "Cocina", _rect(3, 3))


@pytest.mark.evidencia(
    id="BU-97",
    nombre="Unir dos ambientes por un muro compartido",
    requisito="RF-25",
    objetivo="Verificar la transformación rígida: el muro de B queda paralelo al de A, en sentido opuesto y a la distancia del espesor.",
    entrada="Sala 4×3 m y Cocina 3×3 m; muro este de la sala (lado 2) con muro oeste de la cocina (lado 4); espesor 0,15 m",
    esperado="Cocina entre x = 4,15 y 7,15 m, centrada con el muro (y = 0 a 3), sin superposición; área total 21 m²",
)
def test_unir_ambientes(evidencia):
    plan = build_floor_plan([SALA, COCINA], [Join(1, 1, 2, 3, 0.15)])
    cocina = next(r for r in plan.rooms if r.survey_id == 2)
    xs = sorted({round(x, 6) for x, _ in cocina.vertices})
    ys = sorted({round(y, 6) for _, y in cocina.vertices})
    evidencia["obtenido"] = f"x={xs}, y={ys}, advertencias={plan.warnings}"
    assert xs == pytest.approx([4.15, 7.15])
    assert ys == pytest.approx([0.0, 3.0])
    assert not any("superpon" in w for w in plan.warnings)
    assert plan.total_area_m2 == pytest.approx(21.0)


@pytest.mark.evidencia(
    id="BU-98",
    nombre="Unir un ambiente medido con otra orientación",
    requisito="RF-25",
    objetivo="Verificar que la unión funciona aunque el segundo ambiente se haya medido girado 37° y desplazado.",
    entrada="Cocina 3×3 m girada 37° y desplazada (50, −20) m; mismo muro compartido y espesor 0,15 m",
    esperado="El muro unido queda vertical en x = 4,15 m (paralelo al de la sala) y mide 3 m",
)
def test_unir_girado(evidencia):
    girada = Room(2, "Cocina", [(x + 50, y - 20) for x, y in _rot(_rect(3, 3), 37)])
    plan = build_floor_plan([SALA, girada], [Join(1, 1, 2, 3, 0.15)])
    v = next(r for r in plan.rooms if r.survey_id == 2).vertices
    b1, b2 = v[3], v[0]
    evidencia["obtenido"] = f"muro unido: {b1} → {b2}"
    assert b1[0] == pytest.approx(4.15, abs=1e-6) and b2[0] == pytest.approx(4.15, abs=1e-6)
    assert abs(b1[1] - b2[1]) == pytest.approx(3.0, abs=1e-6)


@pytest.mark.evidencia(
    id="BU-99",
    nombre="Advertencias del plano de vivienda",
    requisito="RF-25 / EX-10 / EX-11",
    objetivo="Verificar las advertencias de muros de distinto largo, superposición, escuadra y ambientes sin unir.",
    entrada=("Base 4×4; B 4×6 unido al muro este (largos 4 vs 6); C 12×2 unido al muro norte (se superpone con B); "
             "D con un ángulo de ~95° unido al muro oeste; E sin unión"),
    esperado="Advertencias de largo distinto, superposición, escuadra y ambiente sin unir; E queda fuera del plano",
)
def test_advertencias(evidencia):
    rooms = [
        Room(1, "Base", _rect(4, 4)),
        Room(2, "B", _rect(4, 6)),
        Room(3, "C", _rect(12, 2)),
        Room(4, "D", [(0, 0), (4, 0), (4.35, 4), (0, 4)]),
        Room(5, "E", _rect(2, 2)),
    ]
    plan = build_floor_plan(rooms, [Join(1, 1, 2, 3, 0.15), Join(1, 2, 3, 0, 0.15), Join(1, 3, 4, 1, 0.15)])
    texto = " | ".join(plan.warnings)
    evidencia["obtenido"] = texto
    assert "largo distinto" in texto
    assert "superpon" in texto
    assert "escuadra" in texto
    assert "«E»" in texto and "sin unir" in texto
    assert {r.survey_id for r in plan.rooms} == {1, 2, 3, 4}


@pytest.mark.evidencia(
    id="BU-100",
    nombre="Uniones inválidas",
    requisito="RF-25",
    objetivo="Verificar que se rechaza una unión con un muro o ambiente inexistente, o un espesor fuera de rango.",
    entrada="Muro 9 de la sala; ambiente 99; espesor 2 m",
    esperado="GeometryError en los tres casos",
)
def test_uniones_invalidas(evidencia):
    mensajes = []
    for join in (Join(1, 8, 2, 3, 0.15), Join(1, 1, 99, 3, 0.15), Join(1, 1, 2, 3, 2.0)):
        with pytest.raises(GeometryError) as e:
            build_floor_plan([SALA, COCINA], [join])
        mensajes.append(str(e.value))
    evidencia["obtenido"] = " | ".join(mensajes)


@pytest.mark.evidencia(
    id="BU-101",
    nombre="DXF de la planta completa",
    requisito="RF-26",
    objetivo="Verificar que el DXF de la vivienda trae una polilínea por ambiente, sus nombres y el cuadro de áreas.",
    entrada="Sala y Cocina unidas; escala 1:100",
    esperado="DXF con la capa AMBIENTES, los nombres 'Sala' y 'Cocina' y 'AREA TOTAL'",
)
def test_dxf_vivienda(evidencia):
    plan = build_floor_plan([SALA, COCINA], [Join(1, 1, 2, 3, 0.15)])
    dxf = floor_plan_dxf(plan, "Casa Perez", scale_denominator=100)
    evidencia["obtenido"] = f"{len(dxf)} caracteres"
    assert "AMBIENTES" in dxf and "Sala" in dxf and "Cocina" in dxf and "AREA TOTAL" in dxf


@pytest.mark.evidencia(
    id="BU-102",
    nombre="Unir un ambiente en L por un muro de su entrante",
    requisito="RF-25",
    objetivo="Verificar que el lado de afuera se decide por la normal del muro y no por el centroide, que en un "
    "ambiente cóncavo puede caer del otro lado del muro.",
    entrada="Base 3×4 m (muro este, lado 2) y ambiente en L de 6×6 m con brazo de 2 m, unido por el muro del "
    "entrante x = 2 (lado 4); espesor 0,15 m",
    esperado="El muro unido queda en x = 3,15 m (y = 0 a 4) y el ambiente en L no se superpone con la base",
)
def test_unir_ambiente_concavo(evidencia):
    base = Room(1, "Dormitorio", _rect(3, 4))
    ele = Room(2, "Sala-comedor", [(0.0, 0.0), (6.0, 0.0), (6.0, 2.0), (2.0, 2.0), (2.0, 6.0), (0.0, 6.0)])
    plan = build_floor_plan([base, ele], [Join(1, 1, 2, 3, 0.15)])
    v = next(r for r in plan.rooms if r.survey_id == 2).vertices
    b1, b2 = v[3], v[4]
    evidencia["obtenido"] = f"muro unido: {b1} → {b2}, advertencias={plan.warnings}"
    assert b1[0] == pytest.approx(3.15, abs=1e-6) and b2[0] == pytest.approx(3.15, abs=1e-6)
    assert sorted((b1[1], b2[1])) == pytest.approx([0.0, 4.0], abs=1e-6)
    assert not any("superpon" in w for w in plan.warnings)


@pytest.mark.evidencia(
    id="BU-105",
    nombre="Unir ambientes por la puerta del pasillo",
    requisito="RF-25",
    objetivo="Verificar que, con el punto de la puerta en cada ambiente, se elige el muro más cercano y se alinean "
    "las puertas (no el centro de los muros): varios ambientes en la misma pared del pasillo no se superponen.",
    entrada="Pasillo 10×1,2 m con puertas en (2; 1,2) y (8; 1,2); Sala 4×3 m y Cocina 3×3 m que empiezan en la mitad "
    "de su muro sur (2; 0) y (1,5; 0); espesor 0,15 m",
    esperado="Sala y Cocina sobre el pasillo (y ≥ 1,35), puertas alineadas en x = 2 y x = 8, sin superposición ni "
    "aviso de largo distinto",
)
def test_unir_por_puertas(evidencia):
    pasillo = Room(1, "Pasillo", _rect(10, 1.2))
    sala = Room(2, "Sala", _rect(4, 3))
    cocina = Room(3, "Cocina", _rect(3, 3))
    joins = [
        Join(1, None, 2, None, 0.15, a_point=(2.0, 1.2), b_point=(2.0, 0.0)),
        Join(1, None, 3, None, 0.15, a_point=(8.0, 1.2), b_point=(1.5, 0.0)),
    ]
    plan = build_floor_plan([pasillo, sala, cocina], joins)
    v = {r.name: r.vertices for r in plan.rooms}
    centro = {n: sum(x for x, _ in pts) / len(pts) for n, pts in v.items()}
    evidencia["obtenido"] = (f"y mín sala={min(y for _, y in v['Sala']):.3f}, cocina={min(y for _, y in v['Cocina']):.3f}; "
                             f"centro x sala={centro['Sala']:.2f}, cocina={centro['Cocina']:.2f}; advertencias={plan.warnings}")
    assert min(y for _, y in v["Sala"]) == pytest.approx(1.35, abs=1e-6)
    assert min(y for _, y in v["Cocina"]) == pytest.approx(1.35, abs=1e-6)
    assert centro["Sala"] == pytest.approx(2.0, abs=1e-6)
    assert centro["Cocina"] == pytest.approx(8.0, abs=1e-6)
    assert plan.warnings == []


@pytest.mark.evidencia(
    id="BU-106",
    nombre="Unión sin muro ni puerta",
    requisito="RF-25 / EX-08",
    objetivo="Verificar que cada lado de una unión indica su muro o el punto de su puerta.",
    entrada="Unión Pasillo–Sala sin a_wall ni a_point",
    esperado="GeometryError que pide el muro o la puerta",
)
def test_union_sin_muro_ni_puerta(evidencia):
    with pytest.raises(GeometryError) as exc:
        build_floor_plan([Room(5, "Pasillo", _rect(10, 1.2)), SALA], [Join(5, None, 1, 3, 0.15)])
    evidencia["obtenido"] = str(exc.value)
    assert "puerta" in str(exc.value)
