"""Pruebas unitarias del informe técnico de la medición (CU-10, RF-28)."""

import math
from datetime import UTC, datetime

import pytest

from app.services.gps_core import GpsReading, from_enu, to_enu
from app.services.report_pdf import ReportData, ReportValidation, render_pdf, report_sections
from tests.helpers import ORIGEN_TRUJILLO


def _data(**overrides) -> ReportData:
    base = {
        "project_name": "Pabellón A",
        "survey_name": "Aula 201",
        "mode": "interior",
        "odometry": "arcore",
        "transport": None,
        "device_model": "samsung SM-A256E",
        "created_at": datetime(2026, 11, 10, 15, 30, tzinfo=UTC),
        "vertices": [(0.0, 0.0), (5.0, 0.0), (5.0, 4.0), (0.0, 4.0)],
        "wall_lengths_m": [5.0, 4.0, 5.0, 4.0],
        "interior_angles_deg": [90.0, 90.0, 90.0, 90.0],
        "area_m2": 20.0,
        "perimeter_m": 18.0,
        "closure_error_m": 0.12,
        "scale_denominator": 50,
        "uncertainty": None,
        "validation": None,
        "origin_latlon": None,
        "vertices_latlon": None,
    }
    return ReportData(**{**base, **overrides})


def _text(sections) -> str:
    return "\n".join(
        [s.title for s in sections]
        + [p for s in sections for p in s.paragraphs]
        + [f"{k}: {v}" for s in sections for k, v in s.rows]
    )


@pytest.mark.evidencia(
    id="BU-73",
    nombre="Informe de un ambiente sin validación de campo",
    requisito="RF-28 / EX-13",
    objetivo="Verificar que el informe de un recorrido interior incluye método, resultados y la advertencia de que no fue validado.",
    entrada="Aula 5×4 m medida con ARCore, sin medidas de wincha",
    esperado="Secciones de datos, método (ARCore), resultados (área 20,00 m², cierre 0,12 m) y el texto 'Sin validación de campo'",
)
def test_informe_interior_sin_validacion(evidencia):
    texto = _text(report_sections(_data()))
    evidencia["obtenido"] = " | ".join(s.title for s in report_sections(_data()))
    assert "ARCore" in texto
    assert "20,00 m²" in texto
    assert "0,12 m" in texto
    assert "Sin validación de campo" in texto
    assert "Coordenadas" not in texto


@pytest.mark.evidencia(
    id="BU-74",
    nombre="Informe de un terreno GPS con incertidumbre y coordenadas",
    requisito="RF-28 / RF-21",
    objetivo="Verificar que el informe de un terreno GPS muestra el área con su U95, el método de esquinas fijadas, el cierre y las coordenadas.",
    entrada="Terreno 100×60 m con esquinas fijadas, U95 = 300 m² (5,0 %), cierre 1,8 m",
    esperado="Área '6000,00 ± 300,00 m² (5,0 %)', método 'esquinas fijadas', cierre 1,80 m y una fila de coordenadas por vértice",
)
def test_informe_exterior_con_incertidumbre(evidencia):
    u = {
        "method": "stop_and_go", "area_sigma_m2": 150.0, "area_u95_m2": 300.0, "area_u95_pct": 5.0,
        "perimeter_sigma_m": 2.0, "perimeter_u95_m": 4.0, "perimeter_u95_pct": 1.25, "k": 2.0,
        "vertex_sigma_m": [1.2, 1.2, 1.2, 1.2], "closure_m": 1.8, "closure_consistent": True,
    }
    latlon = [(-8.13, -79.04), (-8.13, -79.0391), (-8.1295, -79.0391), (-8.1295, -79.04)]
    datos = _data(
        mode="exterior", odometry=None, transport="walk", scale_denominator=500,
        vertices=[(0, 0), (100, 0), (100, 60), (0, 60)], wall_lengths_m=[100, 60, 100, 60],
        area_m2=6000.0, perimeter_m=320.0, closure_error_m=0.0, uncertainty=u,
        origin_latlon=(-8.13, -79.04), vertices_latlon=latlon,
    )
    secciones = report_sections(datos)
    texto = _text(secciones)
    coords = next(s for s in secciones if s.title.startswith("6."))
    evidencia["obtenido"] = f"área='{next(v for k, v in secciones[3].rows if k == 'Área')}', filas de coordenadas={len(coords.rows)}"
    assert "6000,00 ± 300,00 m² (5,0 %)" in texto
    assert "esquinas fijadas" in texto
    assert "1,80 m" in texto
    assert len(coords.rows) == 1 + len(latlon)  # origen + vértices


@pytest.mark.evidencia(
    id="BU-75",
    nombre="Informe con validación de wincha",
    requisito="RF-28 / RF-14",
    objetivo="Verificar que el informe resume MAE, RMSE, sesgo y si se cumple la meta de error.",
    entrada="Validación con 4 muros: MAE 0,010 m, RMSE 0,015 m, sesgo +0,005 m, error medio 0,2 %, meta 3 %",
    esperado="Filas MAE 0,010 m, RMSE 0,015 m, 4 muros y 'Cumple la meta (≤ 3 %)'",
)
def test_informe_con_validacion(evidencia):
    val = ReportValidation(n=4, mae_m=0.010, rmse_m=0.015, bias_m=0.005, mean_rel_error_pct=0.2,
                           max_abs_error_m=0.03, meets_target=True, target_pct=3.0, area_error_pct=None)
    texto = _text(report_sections(_data(validation=val)))
    evidencia["obtenido"] = "MAE/RMSE/meta presentes" if "0,010 m" in texto else texto[:200]
    assert "0,010 m" in texto and "0,015 m" in texto
    assert "Cumple la meta (≤ 3 %)" in texto
    assert "Sin validación de campo" not in texto


@pytest.mark.evidencia(
    id="BU-76",
    nombre="Generación del PDF del informe",
    requisito="RF-28",
    objetivo="Verificar que se genera un PDF válido con el plano dibujado.",
    entrada="Aula 5×4 m",
    esperado="Bytes que empiezan con %PDF, terminan con %%EOF y contienen el nombre del recorrido",
)
def test_pdf_valido(evidencia):
    pdf = render_pdf(_data())
    evidencia["obtenido"] = f"{len(pdf)} bytes, cabecera={pdf[:8]!r}"
    assert pdf.startswith(b"%PDF")
    assert pdf.rstrip().endswith(b"%%EOF")
    assert b"Aula 201" in pdf


@pytest.mark.evidencia(
    id="BU-77",
    nombre="Conversión de coordenadas locales a latitud y longitud",
    requisito="RF-28",
    objetivo="Verificar que from_enu es la inversa de to_enu para informar las coordenadas de los vértices.",
    entrada="Punto 300 m al este y 400 m al norte del origen (Trujillo)",
    esperado="Ida y vuelta con error < 1 mm",
)
def test_from_enu_inversa(evidencia):
    lat, lon = from_enu((300.0, 400.0), ORIGEN_TRUJILLO)
    x, y = to_enu([GpsReading(lat, lon)], origin=ORIGEN_TRUJILLO)[0]
    err = math.hypot(x - 300, y - 400)
    evidencia["obtenido"] = f"({lat:.7f}, {lon:.7f}) → ({x:.4f}, {y:.4f}), error={err * 1000:.4f} mm"
    assert err < 1e-3


@pytest.mark.evidencia(
    id="BU-78",
    nombre="Informe de un recorrido antiguo y con caracteres especiales",
    requisito="RF-28",
    objetivo="Verificar que una incertidumbre incompleta (recorridos antiguos) o un nombre con emoji no rompen el informe.",
    entrada="uncertainty = {'method': 'continuous'} y nombre de recorrido 'Terreno 🌳 & <norte>'",
    esperado="Área sin '±', PDF válido y el emoji reemplazado por '?'",
)
def test_informe_robusto(evidencia):
    datos = _data(mode="exterior", odometry=None, uncertainty={"method": "continuous"}, survey_name="Terreno 🌳 & <norte>")
    texto = _text(report_sections(datos))
    pdf = render_pdf(datos)
    evidencia["obtenido"] = f"área sin ±: {'±' not in texto.split('Área: ')[1].splitlines()[0]}, {len(pdf)} bytes"
    assert "20,00 m²" in texto and "±" not in texto.split("Área: ")[1].splitlines()[0]
    assert pdf.startswith(b"%PDF")
    assert b"Terreno ?" in pdf


@pytest.mark.evidencia(
    id="BU-79",
    nombre="Coordenadas del informe con el origen guardado",
    requisito="RF-28",
    objetivo="Verificar que se usa el origen guardado del recorrido y que, si el polígono recalculado no coincide, no se inventan coordenadas.",
    entrada="1) uncertainty con origin_latlon; 2) recorrido antiguo cuyo polígono recalculado tiene otra cantidad de vértices",
    esperado="1) el vértice (300, 400) se convierte desde ese origen; 2) sin coordenadas",
)
def test_coordenadas_origen_guardado(evidencia):
    from app.services.report_service import coordinates
    from tests.helpers import TERRENO_100x60, simulate_stop_and_go

    origen, verts = coordinates([(300.0, 400.0)], {"origin_latlon": list(ORIGEN_TRUJILLO)}, None, "walk")
    esperado = from_enu((300.0, 400.0), ORIGEN_TRUJILLO)
    sin_coords = coordinates([(0.0, 0.0)] * 7, {"method": "stop_and_go"}, simulate_stop_and_go(TERRENO_100x60, seed=5), "walk")
    evidencia["obtenido"] = f"origen={origen}, vértice={verts[0]}, recorrido no coincidente → {sin_coords}"
    assert origen == ORIGEN_TRUJILLO
    assert verts[0] == pytest.approx(esperado)
    assert sin_coords == (None, None)
