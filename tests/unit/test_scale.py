"""Pruebas unitarias de escalas y calibración de planos (RF-10, RF-11)."""

import pytest

from app.services.geometry import GeometryError
from app.services.scale import meters_per_pixel, suggest_scale, to_paper_mm, to_real_m


@pytest.mark.evidencia(
    id="BU-21",
    nombre="Conversión de medida real a papel",
    requisito="RF-10",
    objetivo="Verificar la conversión a escalas 1:50, 1:100 y 1:500 (urbana).",
    entrada="5 m real",
    esperado="1:50 → 100 mm, 1:100 → 50 mm, 1:500 → 10 mm",
)
def test_real_a_papel(evidencia):
    r = {d: to_paper_mm(5, d) for d in (50, 100, 500)}
    evidencia["obtenido"] = str(r)
    assert r == {50: pytest.approx(100), 100: pytest.approx(50), 500: pytest.approx(10)}


@pytest.mark.evidencia(
    id="BU-22",
    nombre="Conversión de papel a medida real",
    requisito="RF-10",
    objetivo="Verificar la conversión inversa en escala urbana 1:500.",
    entrada="37 mm en un plano 1:500",
    esperado="18.5 m",
)
def test_papel_a_real(evidencia):
    r = to_real_m(37, 500)
    evidencia["obtenido"] = f"{r} m"
    assert r == pytest.approx(18.5)


@pytest.mark.evidencia(
    id="BU-23",
    nombre="Rechazo de escala no estándar",
    requisito="RF-10",
    objetivo="Verificar que solo se aceptan escalas normalizadas.",
    entrada="Escala 1:33",
    esperado="GeometryError",
)
def test_escala_invalida(evidencia):
    with pytest.raises(GeometryError) as exc:
        to_paper_mm(1, 33)
    evidencia["obtenido"] = f"GeometryError: {exc.value}"


@pytest.mark.evidencia(
    id="BU-24",
    nombre="Sugerencia de escala para hoja A3",
    requisito="RF-10",
    objetivo="Verificar que se sugiere la escala con más detalle que entra en la hoja.",
    entrada="Aula 6×5 m y terreno 120×80 m; área útil A3 = 380×230 mm",
    esperado="Aula → 1:25 (a 1:20 ocuparía 300×250 mm y no entra) ; terreno → 1:500",
)
def test_sugerir_escala(evidencia):
    aula, terreno = suggest_scale(6, 5), suggest_scale(120, 80)
    evidencia["obtenido"] = f"aula 1:{aula}, terreno 1:{terreno}"
    assert (aula, terreno) == (25, 500)


@pytest.mark.evidencia(
    id="BU-25",
    nombre="Calibración de plano importado",
    requisito="RF-11",
    objetivo="Verificar los metros por píxel a partir de una distancia conocida.",
    entrada="Puntos (100,100) y (500,100) separados 400 px que representan 8 m",
    esperado="0.02 m/px",
)
def test_calibracion(evidencia):
    mpp = meters_per_pixel((100, 100), (500, 100), 8.0)
    evidencia["obtenido"] = f"{mpp} m/px"
    assert mpp == pytest.approx(0.02)
