"""Informe técnico de una medición en PDF (CU-10, RF-28).

El contenido (`report_sections`) se arma como datos y se dibuja aparte (`render_pdf`): así las pruebas
verifican qué dice el informe sin interpretar el PDF.
"""

import io
import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from reportlab.graphics.shapes import Drawing, Line, Polygon, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.services.geometry import Point

MODE_LABELS = {"interior": "Ambiente interior", "exterior": "Terreno exterior (GPS)", "imported": "Plano importado"}
TRANSPORT_LABELS = {"walk": "a pie", "bike": "en bicicleta", "moto": "en moto", "car": "en carro"}


@dataclass(frozen=True)
class ReportValidation:
    """Resumen de la validación con wincha (RF-14)."""

    n: int
    mae_m: float
    rmse_m: float
    bias_m: float
    mean_rel_error_pct: float
    max_abs_error_m: float
    meets_target: bool
    target_pct: float
    area_error_pct: float | None


@dataclass(frozen=True)
class ReportData:
    project_name: str
    survey_name: str
    mode: str  # interior | exterior | imported
    odometry: str | None  # arcore | steps (interior)
    transport: str | None  # walk | bike | moto | car (exterior)
    device_model: str | None
    created_at: datetime
    vertices: list[Point]
    wall_lengths_m: list[float]
    interior_angles_deg: list[float]
    area_m2: float
    perimeter_m: float
    closure_error_m: float
    scale_denominator: int
    uncertainty: dict[str, Any] | None  # ver schemas.project.UncertaintyOut
    validation: ReportValidation | None
    origin_latlon: tuple[float, float] | None
    vertices_latlon: list[tuple[float, float]] | None


@dataclass
class Section:
    title: str
    paragraphs: list[str] = field(default_factory=list)
    rows: list[tuple[str, str]] = field(default_factory=list)
    drawing: bool = False  # en esta sección va el plano


def _n(value: float, decimals: int = 2) -> str:
    """Número con coma decimal (formato peruano)."""
    return f"{value:.{decimals}f}".replace(".", ",")


def _method(d: ReportData) -> str:
    if d.mode == "interior":
        if d.odometry == "steps":
            return ("Odómetro por pasos: el acelerómetro cuenta los pasos (largo de paso calibrado) y el "
                    "giroscopio mide los giros en cada esquina. El trazo se simplificó (RDP), se ortogonalizó y "
                    "se cerró con la regla del tránsito.")
        return ("Odómetro visual con ARCore: la cámara sigue un punto del piso como una rueda de medición y el "
                "usuario marca cada esquina. El trazo se simplificó (RDP), se ortogonalizó y se cerró con la "
                "regla del tránsito.")
    if d.mode == "exterior":
        how = TRANSPORT_LABELS.get(d.transport or "walk", "a pie")
        if d.uncertainty and d.uncertainty.get("method") == "stop_and_go":
            return (f"GPS del celular recorrido {how}, con esquinas fijadas: el usuario se detuvo sobre cada "
                    "esquina y sus lecturas se promediaron (ponderadas por precisión, descartando saltos). "
                    "Se descartaron las lecturas con menos de 6 satélites o señal débil.")
        return (f"GPS del celular recorrido {how} sin detenerse: las lecturas se filtraron (precisión, señal y "
                "saltos de velocidad), se suavizaron con un filtro de Kalman y los lados se ajustaron por "
                "mínimos cuadrados.")
    return "Medición sobre un plano a escala importado, calibrado con una distancia conocida."


def _results(d: ReportData) -> list[tuple[str, str]]:
    u = d.uncertainty
    if u:
        area = f"{_n(d.area_m2)} ± {_n(u['area_u95_m2'])} m² ({_n(u['area_u95_pct'], 1)} %)"
        perimeter = f"{_n(d.perimeter_m)} ± {_n(u['perimeter_u95_m'])} m"
    else:
        area, perimeter = f"{_n(d.area_m2)} m²", f"{_n(d.perimeter_m)} m"
    rows = [("Área", area), ("Perímetro", perimeter)]
    closure = u.get("closure_m") if u else None
    if closure is not None:
        rows.append(("Error de cierre (GPS)", f"{_n(closure)} m"))
        if u.get("closure_consistent") is False:
            rows.append(("Advertencia", "el cierre es mayor de lo esperable: se recomienda volver a medir"))
    elif d.mode != "exterior":
        rows.append(("Error de cierre", f"{_n(d.closure_error_m)} m"))
    rows.append(("Escala del plano", f"1:{d.scale_denominator}"))
    rows += [(f"Lado {i + 1}", f"{_n(length)} m") for i, length in enumerate(d.wall_lengths_m)]
    return rows


def _validation(d: ReportData) -> Section:
    v = d.validation
    s = Section("Validación de campo")
    if v is None:
        s.paragraphs.append(
            "Sin validación de campo: este recorrido no tiene medidas de referencia (wincha u otra fuente). "
            "Los resultados no fueron contrastados con mediciones físicas."
        )
        return s
    s.rows = [
        ("Lados medidos con wincha", str(v.n)),
        ("MAE (error absoluto medio)", f"{_n(v.mae_m, 3)} m"),
        ("RMSE", f"{_n(v.rmse_m, 3)} m"),
        ("Sesgo", f"{'+' if v.bias_m >= 0 else ''}{_n(v.bias_m, 3)} m"),
        ("Error relativo medio", f"{_n(v.mean_rel_error_pct, 1)} %"),
        ("Error absoluto máximo", f"{_n(v.max_abs_error_m, 3)} m"),
    ]
    if v.area_error_pct is not None:
        s.rows.append(("Error del área", f"{_n(v.area_error_pct, 1)} %"))
    target = f"(≤ {_n(v.target_pct, 0)} %)"
    s.rows.append(("Resultado", f"Cumple la meta {target}" if v.meets_target else f"No cumple la meta {target}"))
    return s


def _memoria(d: ReportData) -> str:
    kind = {"interior": "El ambiente", "exterior": "El terreno", "imported": "El plano"}.get(d.mode, "El recorrido")
    text = (f"{kind} «{d.survey_name}» del proyecto «{d.project_name}» se representa como un polígono de "
            f"{len(d.vertices)} lados, con un área de {_n(d.area_m2)} m² y un perímetro de {_n(d.perimeter_m)} m.")
    if d.uncertainty:
        text += (f" Con un 95 % de confianza, el área real está entre {_n(d.area_m2 - d.uncertainty['area_u95_m2'])} "
                 f"y {_n(d.area_m2 + d.uncertainty['area_u95_m2'])} m².")
    return text


def report_sections(d: ReportData) -> list[Section]:
    """Contenido del informe, en orden. Los títulos se numeran según las secciones presentes."""
    general = Section("Datos generales", rows=[
        ("Proyecto", d.project_name),
        ("Recorrido", d.survey_name),
        ("Tipo de medición", MODE_LABELS.get(d.mode, d.mode)),
        ("Dispositivo", d.device_model or "no informado"),
        ("Fecha de medición", d.created_at.strftime("%d/%m/%Y %H:%M")),
        ("Fecha del informe", datetime.now(UTC).strftime("%d/%m/%Y")),
    ])
    sections = [
        general,
        Section("Método de medición", paragraphs=[_method(d)]),
        Section("Plano", paragraphs=[
            (f"Esquema del plano medido. El plano oficial a escala 1:{d.scale_denominator}, con capas y cotas, "
             "se descarga en DXF."),
        ], drawing=True),
        Section("Resultados", rows=_results(d)),
        _validation(d),
    ]
    if d.origin_latlon and d.vertices_latlon:
        rows = [("Origen", f"{d.origin_latlon[0]:.7f}, {d.origin_latlon[1]:.7f}")]
        rows += [(f"Vértice {i + 1}", f"{lat:.7f}, {lon:.7f}") for i, (lat, lon) in enumerate(d.vertices_latlon)]
        sections.append(Section("Coordenadas (WGS84, latitud y longitud)", rows=rows))
    sections.append(Section("Memoria descriptiva", paragraphs=[_memoria(d)]))
    sections.append(Section("Declaración de precisión y alcance", paragraphs=[
        ("La incertidumbre se expresa al 95 % de confianza. Las mediciones con el celular son referenciales: "
         "no reemplazan un levantamiento con estación total o GNSS RTK para linderos, trámites registrales ni "
         "metrados de obra."),
        "Responsable: ______________________________     Firma: ____________________",
    ]))
    for i, s in enumerate(sections, start=1):
        s.title = f"{i}. {s.title}"
    return sections


def _plain(text: str) -> str:
    """Las fuentes estándar del PDF (WinAnsi) no tienen ≤ ni ≥."""
    return text.replace("≤", "<=").replace("≥", ">=")


def _pdf_text(text: str) -> str:
    """Texto para un `Paragraph`, que interpreta marcado: se escapan &, < y >."""
    return _plain(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _plan_drawing(vertices: list[Point], lengths: list[float], width: float = 16 * cm, height: float = 9 * cm) -> Drawing:
    """Esquema del polígono ajustado al recuadro, con el largo de cada lado y una barra de escala."""
    drawing = Drawing(width, height)
    xs, ys = [v[0] for v in vertices], [v[1] for v in vertices]
    dx, dy = max(max(xs) - min(xs), 1e-6), max(max(ys) - min(ys), 1e-6)
    margin = 1.2 * cm
    k = min((width - 2 * margin) / dx, (height - 2 * margin) / dy)
    pts = [(margin + (x - min(xs)) * k, margin + (y - min(ys)) * k) for x, y in vertices]
    drawing.add(Polygon([c for p in pts for c in p], strokeColor=colors.black, strokeWidth=1.2,
                        fillColor=colors.Color(0.9, 0.94, 1)))
    n = len(pts)
    cx, cy = sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n
    for i in range(n):
        (x1, y1), (x2, y2) = pts[i], pts[(i + 1) % n]
        if i < len(lengths):
            # La cota va fuera del polígono: se desplaza desde el centro del lado alejándose del centroide
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            ox, oy = mx - cx, my - cy
            norm = math.hypot(ox, oy) or 1.0
            drawing.add(String(mx + 14 * ox / norm, my + 10 * oy / norm - 2, _n(lengths[i]) + " m",
                               fontName="Helvetica", fontSize=7, textAnchor="middle"))
        vx, vy = x1 - cx, y1 - cy
        vnorm = math.hypot(vx, vy) or 1.0
        drawing.add(String(x1 + 8 * vx / vnorm, y1 + 8 * vy / vnorm - 2, f"V{i + 1}",
                           fontName="Helvetica", fontSize=6, fillColor=colors.grey, textAnchor="middle"))
    # Barra de escala: el largo redondo (1, 2 o 5 × 10ⁿ) más cercano por debajo de 1/4 del lado mayor
    target = max(dx, dy) / 4
    nice = 10 ** math.floor(math.log10(target))
    bar = next(m * nice for m in (5, 2, 1) if m * nice <= target)
    drawing.add(Line(margin, 0.4 * cm, margin + bar * k, 0.4 * cm, strokeWidth=2))
    drawing.add(String(margin + bar * k + 4, 0.3 * cm, f"{_n(bar, 0 if bar >= 1 else 2)} m", fontName="Helvetica", fontSize=7))
    return drawing


def render_pdf(d: ReportData) -> bytes:
    """Dibuja el informe en un PDF A4 (sin compresión de páginas: el texto queda buscable)."""
    styles = getSampleStyleSheet()
    out = io.BytesIO()
    doc = SimpleDocTemplate(
        out, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm, bottomMargin=1.8 * cm,
        title=f"Informe técnico - {d.survey_name}", author="MetriK", pageCompression=0,
    )
    story: list[Any] = [
        Paragraph("Informe técnico de medición", styles["Title"]),
        Paragraph(_pdf_text(f"{d.survey_name} · {d.project_name}"), styles["Heading3"]),
        Spacer(1, 0.3 * cm),
    ]
    for s in report_sections(d):
        story.append(Paragraph(_pdf_text(s.title), styles["Heading2"]))
        story += [Paragraph(_pdf_text(p), styles["BodyText"]) for p in s.paragraphs]
        if s.drawing and len(d.vertices) >= 3:
            story.append(_plan_drawing(d.vertices, d.wall_lengths_m))
        if s.rows:
            table = Table([[_plain(k), _plain(v)] for k, v in s.rows], colWidths=[6 * cm, 11 * cm])
            table.setStyle(TableStyle([
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.Color(0.25, 0.25, 0.25)),
                ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))
            story.append(table)
        story.append(Spacer(1, 0.2 * cm))
    doc.build(story)
    return out.getvalue()
