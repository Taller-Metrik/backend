"""Pruebas unitarias de la exportación DXF (RF-04, RF-12)."""

import io
from collections import Counter

import ezdxf
import pytest

from app.services.dxf_export import DxfMetadata, build_dxf
from app.services.geometry import GeometryError
from tests.helpers import AMBIENTE_L, RECTANGULO_5x4

META = DxfMetadata(title="Aula 201", project="Pabellón A", author="Ana", scale_denominator=50)


def _leer(texto: str):
    return ezdxf.read(io.StringIO(texto))


@pytest.mark.evidencia(
    id="BU-37",
    nombre="DXF válido con capas y unidades en metros",
    requisito="RF-12",
    objetivo="Verificar que el DXF generado se puede abrir y tiene las capas y unidades correctas.",
    entrada="Rectángulo 5×4 m, escala 1:50",
    esperado="Versión AC1024 (R2010), $INSUNITS=6, capas MUROS, COTAS, TEXTO, ROTULO",
)
def test_dxf_capas_y_unidades(evidencia):
    doc = _leer(build_dxf(RECTANGULO_5x4, META))
    capas = {layer.dxf.name for layer in doc.layers}
    evidencia["obtenido"] = f"versión={doc.dxfversion}, INSUNITS={doc.header['$INSUNITS']}, capas={sorted(capas)}"
    assert doc.dxfversion == "AC1024"
    assert doc.header["$INSUNITS"] == 6
    assert {"MUROS", "COTAS", "TEXTO", "ROTULO"} <= capas


@pytest.mark.evidencia(
    id="BU-38",
    nombre="Muros como polilínea cerrada en metros reales",
    requisito="RF-04",
    objetivo="Verificar que los muros se exportan como LWPOLYLINE cerrada con las coordenadas reales.",
    entrada="Ambiente en L (6 vértices)",
    esperado="1 polilínea cerrada en MUROS con los 6 vértices exactos",
)
def test_dxf_muros(evidencia):
    msp = _leer(build_dxf(AMBIENTE_L, META)).modelspace()
    muros = msp.query('LWPOLYLINE[layer=="MUROS"]')
    pts = [(round(p[0], 6), round(p[1], 6)) for p in muros[0].get_points("xy")]
    evidencia["obtenido"] = f"polilíneas={len(muros)}, cerrada={muros[0].closed}, vértices={pts}"
    assert len(muros) == 1 and muros[0].closed
    assert pts == [(float(x), float(y)) for x, y in AMBIENTE_L]


@pytest.mark.evidencia(
    id="BU-39",
    nombre="Una cota por muro con la medida real, fuera del ambiente",
    requisito="RF-10, RF-12",
    objetivo="Verificar las cotas alineadas: una por muro, con su medida y ubicadas hacia el exterior.",
    entrada="Ambiente en L en sentido antihorario y horario",
    esperado="6 cotas con medidas [6, 3, 3, 2, 3, 5] m en ambos sentidos, todas fuera del polígono",
)
def test_dxf_cotas(evidencia):
    from app.services.geometry import Point

    def dentro(p: Point, poly: list[Point]) -> bool:
        x, y, c = p[0], p[1], False
        for i in range(len(poly)):
            (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % len(poly)]
            if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                c = not c
        return c

    resultados = []
    for poly in (AMBIENTE_L, list(reversed(AMBIENTE_L))):
        dims = _leer(build_dxf(poly, META)).modelspace().query("DIMENSION")
        medidas = sorted(round(d.get_measurement(), 3) for d in dims)
        fuera = all(not dentro((d.dxf.defpoint[0], d.dxf.defpoint[1]), poly) for d in dims)
        resultados.append((medidas, fuera))
    evidencia["obtenido"] = f"antihorario={resultados[0]}, horario={resultados[1]}"
    for medidas, fuera in resultados:
        assert medidas == [2.0, 3.0, 3.0, 3.0, 5.0, 6.0]
        assert fuera


@pytest.mark.evidencia(
    id="BU-40",
    nombre="Rótulo con título, escala, área y perímetro",
    requisito="RF-10",
    objetivo="Verificar que el plano incluye los textos del rótulo y los totales.",
    entrada="Rectángulo 5×4 m, escala 1:50, título 'Aula 201'",
    esperado="Textos con 'Aula 201', 'Escala 1:50', 'Area: 20.00 m2', 'Perimetro: 18.00 m'",
)
def test_dxf_rotulo(evidencia):
    textos = [t.dxf.text for t in _leer(build_dxf(RECTANGULO_5x4, META)).modelspace().query("TEXT")]
    evidencia["obtenido"] = " | ".join(textos)
    contenido = " ".join(textos)
    for esperado in ("Aula 201", "Escala 1:50", "Area: 20.00 m2", "Perimetro: 18.00 m"):
        assert esperado in contenido


@pytest.mark.evidencia(
    id="BU-41",
    nombre="Tamaño del texto según la escala",
    requisito="RF-10",
    objetivo="Verificar que el texto mide 2.5 mm en el papel para cualquier escala.",
    entrada="Mismo plano a 1:50 y a 1:500",
    esperado="Altura en modelo 0.125 m (1:50) y 1.25 m (1:500)",
)
def test_dxf_texto_escalado(evidencia):
    alturas = {}
    for d in (50, 500):
        meta = DxfMetadata(title="T", project="P", author="A", scale_denominator=d)
        texto = _leer(build_dxf(RECTANGULO_5x4, meta)).modelspace().query('TEXT[layer=="TEXTO"]')[0]
        alturas[d] = round(texto.dxf.height, 4)
    evidencia["obtenido"] = f"1:50 → {alturas[50]} m, 1:500 → {alturas[500]} m"
    assert alturas == {50: 0.125, 500: 1.25}


@pytest.mark.evidencia(
    id="BU-42",
    nombre="Rechazo de escala no estándar en DXF",
    requisito="RF-10",
    objetivo="Verificar que no se genera un DXF con escala inválida.",
    entrada="Escala 1:33",
    esperado="GeometryError",
)
def test_dxf_escala_invalida(evidencia):
    with pytest.raises(GeometryError) as exc:
        build_dxf(RECTANGULO_5x4, DxfMetadata(title="T", project="P", author="A", scale_denominator=33))
    evidencia["obtenido"] = f"GeometryError: {exc.value}"
