"""Exportación del plano a DXF (estándar abierto CAD). Ver docs/03-algoritmos.md, sección 7.

- Coordenadas en metros reales ($INSUNITS = 6); la escala se aplica al imprimir y se
  usa para dimensionar textos, flechas y el rótulo como se verían en el papel.
- Capas: MUROS, COTAS, TEXTO, ROTULO.
"""

import io
from dataclasses import dataclass
from datetime import date

import ezdxf
from ezdxf.enums import TextEntityAlignment

from app.services.geometry import Point, analyze
from app.services.scale import validate_scale

LAYERS = {
    "MUROS": {"color": 7, "lineweight": 50},
    "COTAS": {"color": 1, "lineweight": 18},
    "TEXTO": {"color": 3, "lineweight": 18},
    "ROTULO": {"color": 5, "lineweight": 25},
}
TEXT_HEIGHT_MM = 2.5  # altura de texto en el papel
TITLE_TEXT_HEIGHT_MM = 4.0
DIM_OFFSET_MM = 8.0  # separación de la cota respecto al muro, en el papel


@dataclass(frozen=True)
class DxfMetadata:
    title: str
    project: str
    author: str
    scale_denominator: int
    survey_date: date | None = None


def _paper(mm: float, denominator: int) -> float:
    """Milímetros en el papel → metros en el modelo."""
    return mm * denominator / 1000.0


def build_dxf(vertices: list[Point], meta: DxfMetadata) -> str:
    """Genera el DXF del plano y lo devuelve como texto."""
    denominator = validate_scale(meta.scale_denominator)
    analysis = analyze(vertices)
    poly = analysis.vertices
    ccw = analysis.orientation == "antihorario"

    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = 6  # metros
    doc.header["$MEASUREMENT"] = 1  # métrico
    doc.header["$LUNITS"] = 2  # decimal
    for name, attrs in LAYERS.items():
        doc.layers.add(name, color=attrs["color"], lineweight=attrs["lineweight"])

    text_h = _paper(TEXT_HEIGHT_MM, denominator)
    dimstyle = doc.dimstyles.new("METRIK")
    dimstyle.dxf.dimtxt = text_h
    dimstyle.dxf.dimasz = text_h
    dimstyle.dxf.dimexo = text_h / 2
    dimstyle.dxf.dimexe = text_h / 2
    dimstyle.dxf.dimgap = text_h / 4
    dimstyle.dxf.dimdec = 2
    dimstyle.dxf.dimtad = 1
    dimstyle.dxf.dimpost = "<> m"

    msp = doc.modelspace()

    # Muros
    msp.add_lwpolyline(poly, close=True, dxfattribs={"layer": "MUROS"})

    # Cotas alineadas por muro, desplazadas hacia afuera del ambiente
    offset = _paper(DIM_OFFSET_MM, denominator)
    n = len(poly)
    for i in range(n):
        p1, p2 = poly[i], poly[(i + 1) % n]
        # ezdxf coloca la cota a la izquierda de p1→p2 con distancia positiva.
        # En sentido antihorario el exterior está a la derecha → distancia negativa.
        distance = -offset if ccw else offset
        dim = msp.add_aligned_dim(
            p1=p1, p2=p2, distance=distance, dimstyle="METRIK", dxfattribs={"layer": "COTAS"}
        )
        dim.render()

    # Área y perímetro en el centro del ambiente
    cx = sum(p[0] for p in poly) / n
    cy = sum(p[1] for p in poly) / n
    for k, line in enumerate(
        (f"Area: {analysis.area_m2:.2f} m2", f"Perimetro: {analysis.perimeter_m:.2f} m")
    ):
        msp.add_text(line, height=text_h, dxfattribs={"layer": "TEXTO"}).set_placement(
            (cx, cy - k * text_h * 1.8), align=TextEntityAlignment.MIDDLE_CENTER
        )

    # Rótulo debajo del plano
    min_x = min(p[0] for p in poly)
    max_x = max(p[0] for p in poly)
    min_y = min(p[1] for p in poly)
    width = max(max_x - min_x, _paper(120, denominator))
    height = _paper(28, denominator)
    top = min_y - _paper(20, denominator)
    x0, y0 = min_x, top - height
    msp.add_lwpolyline(
        [(x0, y0), (x0 + width, y0), (x0 + width, top), (x0, top)], close=True, dxfattribs={"layer": "ROTULO"}
    )
    lines = [
        (meta.title, _paper(TITLE_TEXT_HEIGHT_MM, denominator)),
        (f"Proyecto: {meta.project}", text_h),
        (f"Escala 1:{denominator}   Unidades: metros", text_h),
        (f"Autor: {meta.author}   Fecha: {(meta.survey_date or date.today()).isoformat()}", text_h),
        ("Generado por MetriK", text_h),
    ]
    y = top - _paper(5, denominator)
    for text, h in lines:
        msp.add_text(text, height=h, dxfattribs={"layer": "ROTULO"}).set_placement(
            (x0 + _paper(4, denominator), y), align=TextEntityAlignment.MIDDLE_LEFT
        )
        y -= h * 1.6

    stream = io.StringIO()
    doc.write(stream)
    return stream.getvalue()
