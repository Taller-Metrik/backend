"""Pruebas unitarias del cálculo del margen de error (RF-13, RF-14)."""

import math

import pytest

from app.services.geometry import GeometryError
from app.services.validation import compare_wall, error_report, real_value, to_csv


@pytest.mark.evidencia(
    id="BU-43",
    nombre="Valor real como promedio de lecturas de wincha",
    requisito="RF-13",
    objetivo="Verificar el promedio de lecturas y el aviso cuando difieren más de 1 cm.",
    entrada="[5.002, 4.998] y [5.00, 5.03]",
    esperado="5.000 m sin aviso; 5.015 m con aviso de tercera lectura",
)
def test_valor_real(evidencia):
    a = real_value([5.002, 4.998])
    b = real_value([5.00, 5.03])
    evidencia["obtenido"] = f"{a[0]:.3f} m aviso={a[1]}; {b[0]:.3f} m aviso={b[1]}"
    assert a[0] == pytest.approx(5.0) and a[1] is False
    assert b[0] == pytest.approx(5.015) and b[1] is True


@pytest.mark.evidencia(
    id="BU-44",
    nombre="Error absoluto y relativo de un muro",
    requisito="RF-14",
    objetivo="Verificar el error de la app respecto a la wincha en un muro.",
    entrada="App 5.08 m; wincha [5.00, 5.00]",
    esperado="error=+0.08 m, error relativo=1.6 %",
)
def test_error_muro(evidencia):
    c = compare_wall(0, 5.08, [5.0, 5.0])
    evidencia["obtenido"] = f"error={c.error_m:+.3f} m, relativo={c.rel_error_pct:.2f} %"
    assert c.error_m == pytest.approx(0.08)
    assert c.rel_error_pct == pytest.approx(1.6)


@pytest.mark.evidencia(
    id="BU-45",
    nombre="MAE, RMSE, sesgo y desviación estándar",
    requisito="RF-14",
    objetivo="Verificar las métricas agregadas con valores calculados a mano.",
    entrada="Errores de +0.10, −0.10, +0.20, 0.00 m sobre muros de 5 m",
    esperado="MAE=0.10, RMSE=0.1225, sesgo=0.05, desv.=0.1291, error rel. medio=2.0 %",
)
def test_metricas_agregadas(evidencia):
    walls = [compare_wall(i, 5 + e, [5.0]) for i, e in enumerate((0.10, -0.10, 0.20, 0.0))]
    r = error_report(walls)
    evidencia["obtenido"] = (
        f"MAE={r.mae_m:.4f}, RMSE={r.rmse_m:.4f}, sesgo={r.bias_m:.4f}, desv={r.std_m:.4f}, "
        f"rel={r.mean_rel_error_pct:.2f} %, cumple 3 %={r.meets_target}"
    )
    assert r.mae_m == pytest.approx(0.10)
    assert r.rmse_m == pytest.approx(math.sqrt(0.015))
    assert r.bias_m == pytest.approx(0.05)
    assert r.std_m == pytest.approx(0.129099, rel=1e-4)
    assert r.mean_rel_error_pct == pytest.approx(2.0)
    assert r.meets_target is True


@pytest.mark.evidencia(
    id="BU-46",
    nombre="Error de área y criterio de aceptación",
    requisito="RF-14 / RNF-01",
    objetivo="Verificar el error de área y que se marca incumplimiento si el error relativo medio supera 3 %.",
    entrada="Muros con 5 % de error; área app 21.0 vs real 20.0 m²",
    esperado="Error de área 5 %, meets_target=False",
)
def test_area_y_criterio(evidencia):
    walls = [compare_wall(0, 5.25, [5.0]), compare_wall(1, 4.2, [4.0])]
    r = error_report(walls, measured_area_m2=21.0, real_area_m2=20.0)
    evidencia["obtenido"] = f"área={r.area_error_pct:.2f} %, rel medio={r.mean_rel_error_pct:.2f} %, cumple={r.meets_target}"
    assert r.area_error_pct == pytest.approx(5.0)
    assert r.meets_target is False


@pytest.mark.evidencia(
    id="BU-47",
    nombre="Planilla CSV compatible con Excel en español",
    requisito="RF-14",
    objetivo="Verificar el formato del CSV: BOM UTF-8, separador ';' y coma decimal.",
    entrada="Un muro con lecturas [5.0, 5.01], app 5.08 m",
    esperado="Encabezado con 'error_rel_pct', separador ';' y valores como '5,0800'",
)
def test_csv(evidencia):
    c = compare_wall(0, 5.08, [5.0, 5.01])
    texto = to_csv([{"project": "P", "survey": "Aula", "mode": "interior", **c.__dict__}])
    lineas = texto.lstrip("﻿").strip().split("\n")
    evidencia["obtenido"] = f"BOM={texto.startswith(chr(0xFEFF))}, filas={lineas}"
    assert texto.startswith("﻿")
    assert lineas[0].split(";")[-1] == "error_rel_pct"
    assert "5,0800" in lineas[1] and lineas[1].startswith("P;Aula;interior;1;")


@pytest.mark.evidencia(
    id="BU-48",
    nombre="Rechazo de lecturas inválidas y reporte vacío",
    requisito="RF-13",
    objetivo="Verificar que no se aceptan lecturas no positivas ni reportes sin datos.",
    entrada="Lecturas [0, 5] y lista de muros vacía",
    esperado="GeometryError en ambos casos",
)
def test_validaciones(evidencia):
    errores = []
    with pytest.raises(GeometryError) as e1:
        real_value([0, 5])
    errores.append(str(e1.value))
    with pytest.raises(GeometryError) as e2:
        error_report([])
    errores.append(str(e2.value))
    evidencia["obtenido"] = " | ".join(errores)
