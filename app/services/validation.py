"""Margen de error: comparación de la app con medidas reales (docs/05-protocolo-validacion.md)."""

import csv
import io
import math
import statistics
from dataclasses import dataclass

from app.services.geometry import GeometryError

READINGS_TOLERANCE_M = 0.01  # si dos lecturas de wincha difieren más, se pide una tercera


@dataclass(frozen=True)
class WallComparison:
    wall_index: int
    measured_m: float
    real_m: float
    error_m: float
    abs_error_m: float
    rel_error_pct: float
    readings_m: list[float]
    needs_extra_reading: bool


@dataclass(frozen=True)
class ErrorReport:
    n: int
    mae_m: float
    rmse_m: float
    bias_m: float
    std_m: float
    mean_rel_error_pct: float
    max_abs_error_m: float
    max_rel_error_pct: float
    area_error_pct: float | None
    meets_target: bool
    target_pct: float
    walls: list[WallComparison]


def real_value(readings: list[float]) -> tuple[float, bool]:
    """Valor real = promedio de las lecturas de wincha. Indica si hace falta otra lectura."""
    if not readings or any(r <= 0 for r in readings):
        raise GeometryError("Las lecturas de wincha deben ser positivas")
    spread = max(readings) - min(readings)
    return statistics.fmean(readings), len(readings) < 3 and spread > READINGS_TOLERANCE_M


def compare_wall(wall_index: int, measured_m: float, readings: list[float]) -> WallComparison:
    real, extra = real_value(readings)
    error = measured_m - real
    return WallComparison(
        wall_index=wall_index,
        measured_m=measured_m,
        real_m=real,
        error_m=error,
        abs_error_m=abs(error),
        rel_error_pct=100 * abs(error) / real,
        readings_m=list(readings),
        needs_extra_reading=extra,
    )


def error_report(
    walls: list[WallComparison],
    *,
    measured_area_m2: float | None = None,
    real_area_m2: float | None = None,
    target_pct: float = 3.0,
) -> ErrorReport:
    """Métricas de error (MAE, RMSE, sesgo, desviación, error relativo) sobre un conjunto de muros."""
    if not walls:
        raise GeometryError("No hay medidas reales registradas para comparar")
    errors = [w.error_m for w in walls]
    rel = [w.rel_error_pct for w in walls]
    area_error = None
    if measured_area_m2 is not None and real_area_m2:
        area_error = 100 * abs(measured_area_m2 - real_area_m2) / real_area_m2
    mean_rel = statistics.fmean(rel)
    return ErrorReport(
        n=len(walls),
        mae_m=statistics.fmean(abs(e) for e in errors),
        rmse_m=math.sqrt(statistics.fmean(e * e for e in errors)),
        bias_m=statistics.fmean(errors),
        std_m=statistics.stdev(errors) if len(errors) > 1 else 0.0,
        mean_rel_error_pct=mean_rel,
        max_abs_error_m=max(abs(e) for e in errors),
        max_rel_error_pct=max(rel),
        area_error_pct=area_error,
        meets_target=mean_rel <= target_pct,
        target_pct=target_pct,
        walls=walls,
    )


CSV_HEADER = [
    "proyecto", "recorrido", "modo", "muro", "lectura_1_m", "lectura_2_m", "lectura_3_m",
    "real_m", "app_m", "error_m", "error_abs_m", "error_rel_pct",
]


def to_csv(rows: list[dict]) -> str:
    """CSV (separador ';' y coma decimal, para abrirlo directo en Excel en español)."""
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";", lineterminator="\n")
    writer.writerow(CSV_HEADER)

    def fmt(value: float | None) -> str:
        return "" if value is None else f"{value:.4f}".replace(".", ",")

    for r in rows:
        readings = list(r["readings_m"]) + [None] * (3 - len(r["readings_m"]))
        writer.writerow(
            [r["project"], r["survey"], r["mode"], r["wall_index"] + 1, *(fmt(x) for x in readings[:3]),
             fmt(r["real_m"]), fmt(r["measured_m"]), fmt(r["error_m"]), fmt(r["abs_error_m"]), fmt(r["rel_error_pct"])]
        )
    return "﻿" + out.getvalue()  # BOM para que Excel detecte UTF-8
