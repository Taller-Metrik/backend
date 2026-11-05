"""Validación de recorridos GPS contra una referencia externa (no se puede medir con wincha).

Referencias: cancha con medidas oficiales, plano catastral/SUNARP, imagen satelital,
tramo base medido con wincha o GPS profesional (RTK). Ver docs/05 §9.
"""

import math
from dataclasses import dataclass

from app.services.geometry import GeometryError, analyze
from app.services.gps import TRANSPORT_PROFILES, GpsReading, filter_by_accuracy, to_enu

REFERENCE_TYPES = {
    "cancha": "Cancha con medidas oficiales",
    "catastro": "Plano catastral / SUNARP",
    "satelital": "Imagen satelital",
    "tramo_base": "Tramo base medido con wincha",
    "rtk": "GPS profesional (RTK) / hito geodésico",
}
TARGET_AREA_ERROR_PCT = 5.0


@dataclass(frozen=True)
class GpsReferenceReport:
    reference_type: str
    reference_label: str
    measured_area_m2: float
    real_area_m2: float | None
    area_error_pct: float | None
    measured_perimeter_m: float
    real_perimeter_m: float | None
    perimeter_error_pct: float | None
    vertex_errors_m: list[float]
    vertex_mae_m: float | None
    meets_target: bool | None
    target_pct: float


def _pct(measured: float, real: float | None) -> float | None:
    return None if not real else 100 * abs(measured - real) / real


def evaluate(
    *,
    reference_type: str,
    measured_vertices: list[tuple[float, float]],
    gps_points: list[dict],
    transport: str,
    real_area_m2: float | None,
    real_perimeter_m: float | None,
    reference_vertices: list[dict] | None,
) -> GpsReferenceReport:
    if reference_type not in REFERENCE_TYPES:
        raise GeometryError(f"Tipo de referencia no válido: {reference_type}")
    measured = analyze(measured_vertices)
    vertex_errors: list[float] = []
    if reference_vertices:
        if len(reference_vertices) < 3:
            raise GeometryError("La referencia necesita al menos 3 esquinas")
        profile = TRANSPORT_PROFILES.get(transport, TRANSPORT_PROFILES["walk"])
        readings = [GpsReading(**{k: p.get(k) for k in ("lat", "lon", "accuracy_m", "timestamp_s")}) for p in gps_points]
        valid, _ = filter_by_accuracy(readings, profile.max_accuracy_m)
        if not valid:
            raise GeometryError("El recorrido no tiene lecturas GPS válidas")
        ref_xy = to_enu([GpsReading(v["lat"], v["lon"]) for v in reference_vertices], origin=(valid[0].lat, valid[0].lon))
        ref = analyze(ref_xy)
        real_area_m2 = real_area_m2 or ref.area_m2
        real_perimeter_m = real_perimeter_m or ref.perimeter_m
        vertex_errors = [min(math.dist(r, m) for m in measured.vertices) for r in ref.vertices]
    area_err = _pct(measured.area_m2, real_area_m2)
    return GpsReferenceReport(
        reference_type=reference_type,
        reference_label=REFERENCE_TYPES[reference_type],
        measured_area_m2=measured.area_m2,
        real_area_m2=real_area_m2,
        area_error_pct=area_err,
        measured_perimeter_m=measured.perimeter_m,
        real_perimeter_m=real_perimeter_m,
        perimeter_error_pct=_pct(measured.perimeter_m, real_perimeter_m),
        vertex_errors_m=vertex_errors,
        vertex_mae_m=sum(vertex_errors) / len(vertex_errors) if vertex_errors else None,
        meets_target=None if area_err is None else area_err <= TARGET_AREA_ERROR_PCT,
        target_pct=TARGET_AREA_ERROR_PCT,
    )
