"""Pruebas unitarias del cálculo geométrico (RF-06, RF-07)."""

import pytest

from app.services.geometry import GeometryError, analyze, area, euclidean, interior_angles, is_simple, manhattan, perimeter
from tests.helpers import AMBIENTE_L, RECTANGULO_5x4


@pytest.mark.evidencia(
    id="BU-06",
    nombre="Área de un rectángulo por Shoelace",
    requisito="RF-06",
    objetivo="Verificar la fórmula de Gauss (Shoelace) en un polígono convexo.",
    entrada="Rectángulo (0,0), (5,0), (5,4), (0,4)",
    esperado="20.0 m²",
)
def test_area_rectangulo(evidencia):
    resultado = area(RECTANGULO_5x4)
    evidencia["obtenido"] = f"{resultado} m²"
    assert resultado == pytest.approx(20.0)


@pytest.mark.evidencia(
    id="BU-07",
    nombre="Área de un ambiente cóncavo en L",
    requisito="RF-06",
    objetivo="Verificar que el área de un polígono cóncavo no se infla (no se usa envolvente convexa).",
    entrada="Ambiente en L de 6×5 m con un recorte de 3×2 m",
    esperado="24.0 m² (la envolvente convexa daría 30 m²)",
)
def test_area_concavo_l(evidencia):
    resultado = area(AMBIENTE_L)
    evidencia["obtenido"] = f"{resultado} m²"
    assert resultado == pytest.approx(24.0)


@pytest.mark.evidencia(
    id="BU-08",
    nombre="El área no depende del sentido del recorrido",
    requisito="RF-06",
    objetivo="Verificar que recorrer en sentido horario o antihorario da la misma área.",
    entrada="Ambiente en L en ambos sentidos",
    esperado="24.0 m² en ambos casos y orientación detectada correctamente",
)
def test_area_independiente_del_sentido(evidencia):
    horario = list(reversed(AMBIENTE_L))
    a1, a2 = analyze(AMBIENTE_L), analyze(horario)
    evidencia["obtenido"] = f"{a1.area_m2} m² ({a1.orientation}), {a2.area_m2} m² ({a2.orientation})"
    assert a1.area_m2 == pytest.approx(a2.area_m2) == pytest.approx(24.0)
    assert (a1.orientation, a2.orientation) == ("antihorario", "horario")


@pytest.mark.evidencia(
    id="BU-09",
    nombre="Perímetro de un rectángulo",
    requisito="RF-06",
    objetivo="Verificar la suma de longitudes de los muros.",
    entrada="Rectángulo 5×4 m",
    esperado="18.0 m",
)
def test_perimetro(evidencia):
    resultado = perimeter(RECTANGULO_5x4)
    evidencia["obtenido"] = f"{resultado} m"
    assert resultado == pytest.approx(18.0)


@pytest.mark.evidencia(
    id="BU-10",
    nombre="Ángulos interiores y vértice cóncavo",
    requisito="RF-06",
    objetivo="Verificar que se detecta el vértice cóncavo (270°) en un ambiente en L, en ambos sentidos.",
    entrada="Ambiente en L (antihorario y horario)",
    esperado="Cinco ángulos de 90°, uno de 270° y suma = (n−2)·180 = 720°",
)
def test_angulos_concavo(evidencia):
    ccw = interior_angles(AMBIENTE_L)
    cw = interior_angles(list(reversed(AMBIENTE_L)))
    evidencia["obtenido"] = f"antihorario={[round(a) for a in ccw]}, horario={[round(a) for a in cw]}"
    assert sorted(round(a) for a in ccw) == [90, 90, 90, 90, 90, 270]
    assert sorted(round(a) for a in cw) == [90, 90, 90, 90, 90, 270]
    assert sum(ccw) == pytest.approx(720.0)


@pytest.mark.evidencia(
    id="BU-11",
    nombre="Distancia Euclidiana vs Manhattan",
    requisito="RF-07",
    objetivo="Verificar ambas métricas entre dos puntos.",
    entrada="A=(0,0), B=(3,4)",
    esperado="Euclidiana 5.0 m, Manhattan 7.0 m",
)
def test_distancias(evidencia):
    e, m = euclidean((0, 0), (3, 4)), manhattan((0, 0), (3, 4))
    evidencia["obtenido"] = f"Euclidiana={e} m, Manhattan={m} m"
    assert e == pytest.approx(5.0)
    assert m == pytest.approx(7.0)


@pytest.mark.evidencia(
    id="BU-12",
    nombre="Detección de polígono autointersectado",
    requisito="RF-06 / EX-06",
    objetivo="Verificar que un recorrido en forma de '8' (moño) se marca como no simple.",
    entrada="Vértices (0,0), (4,4), (4,0), (0,4)",
    esperado="is_simple = False; el rectángulo normal es simple",
)
def test_autointerseccion(evidencia):
    mono = is_simple([(0, 0), (4, 4), (4, 0), (0, 4)])
    normal = is_simple(RECTANGULO_5x4)
    evidencia["obtenido"] = f"moño simple={mono}, rectángulo simple={normal}"
    assert mono is False and normal is True


@pytest.mark.evidencia(
    id="BU-13",
    nombre="Rechazo de polígono con menos de 3 vértices",
    requisito="EX-05",
    objetivo="Verificar que no se calcula área con 2 vértices o con vértices repetidos.",
    entrada="[(0,0),(1,0)] y [(0,0),(0,0),(1,1),(0,0)]",
    esperado="GeometryError en ambos casos",
)
def test_menos_de_tres_vertices(evidencia):
    errores = []
    for poly in ([(0, 0), (1, 0)], [(0, 0), (0, 0), (1, 1), (0, 0)]):
        with pytest.raises(GeometryError) as exc:
            area(poly)
        errores.append(str(exc.value))
    evidencia["obtenido"] = f"GeometryError x{len(errores)}: {errores[0]}"
