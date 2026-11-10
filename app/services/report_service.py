"""Arma los datos del informe técnico (CU-10) a partir de un recorrido guardado."""

import logging
from dataclasses import fields
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.models.survey import SurveyMode
from app.models.user import User
from app.services.geometry import GeometryError, Point
from app.services.gps import GpsReading, gps_polygon
from app.services.gps_core import from_enu
from app.services.project_service import ProjectService, SurveyService
from app.services.report_pdf import ReportData, ReportValidation, render_pdf
from app.services.validation_service import ValidationService

logger = logging.getLogger(__name__)
_READING_FIELDS = {f.name for f in fields(GpsReading)}

LatLon = tuple[float, float]


class ReportService:
    """Informe técnico de un recorrido del usuario (lectura; no modifica la base de datos)."""

    def __init__(self, db: AsyncSession, user: User) -> None:
        self.db = db
        self.user = user

    async def data(self, survey_id: int) -> ReportData:
        """Datos del informe. Lanza NotFoundError si el recorrido no existe o es de otro usuario."""
        survey = await SurveyService(self.db, self.user).get(survey_id)
        project = await ProjectService(self.db, self.user).get(survey.project_id)
        validation = await self._validation(survey_id)
        capture = survey.capture or {}
        vertices: list[Point] = [(float(v[0]), float(v[1])) for v in survey.vertices]
        origin, vertices_latlon = None, None
        if survey.mode == SurveyMode.EXTERIOR:
            # Puede recalcular el polígono GPS (CPU): fuera del event loop
            origin, vertices_latlon = await run_in_threadpool(
                coordinates, vertices, survey.uncertainty, survey.gps_points, capture.get("transport") or "walk"
            )
        return ReportData(
            project_name=project.name,
            survey_name=survey.name,
            mode=survey.mode.value,
            odometry=capture.get("odometry"),
            transport=capture.get("transport"),
            device_model=survey.device_model,
            created_at=survey.measured_at or survey.created_at,
            vertices=vertices,
            wall_lengths_m=list(survey.wall_lengths_m),
            interior_angles_deg=list(survey.interior_angles_deg),
            area_m2=survey.area_m2,
            perimeter_m=survey.perimeter_m,
            closure_error_m=survey.closure_error_m,
            scale_denominator=survey.scale_denominator,
            uncertainty=survey.uncertainty,
            validation=validation,
            origin_latlon=origin,
            vertices_latlon=vertices_latlon,
        )

    async def pdf(self, survey_id: int) -> bytes:
        data = await self.data(survey_id)
        return await run_in_threadpool(render_pdf, data)  # ReportLab es CPU: fuera del event loop

    async def _validation(self, survey_id: int) -> ReportValidation | None:
        try:
            _, r = await ValidationService(self.db, self.user).survey_report(survey_id)
        except GeometryError:  # sin medidas de wincha registradas (EX-13)
            return None
        return ReportValidation(
            n=r.n, mae_m=r.mae_m, rmse_m=r.rmse_m, bias_m=r.bias_m, mean_rel_error_pct=r.mean_rel_error_pct,
            max_abs_error_m=r.max_abs_error_m, meets_target=r.meets_target, target_pct=r.target_pct,
            area_error_pct=r.area_error_pct,
        )


def coordinates(
    vertices: list[Point],
    uncertainty: dict[str, Any] | None,
    gps_points: list[dict[str, Any]] | None,
    transport: str,
) -> tuple[LatLon | None, list[LatLon] | None]:
    """Origen y latitud/longitud de los vértices de un recorrido GPS.

    Los vértices se guardan en metros respecto del origen del polígono. Los recorridos nuevos guardan ese
    origen en `uncertainty.origin_latlon`; para los anteriores se recalcula el polígono con el mismo
    procesamiento y solo se usa si da la misma cantidad de vértices (si no, no se informan coordenadas).
    """
    stored = (uncertainty or {}).get("origin_latlon")
    if stored and len(stored) == 2:
        origin: LatLon = (float(stored[0]), float(stored[1]))
    elif gps_points:
        readings = [GpsReading(**{k: v for k, v in p.items() if k in _READING_FIELDS}) for p in gps_points]
        try:
            poly = gps_polygon(readings, transport=transport)
        except GeometryError as exc:
            logger.warning("No se pudo recalcular el origen GPS del informe: %s", exc)
            return None, None
        if len(poly.vertices) != len(vertices):
            logger.warning("El polígono recalculado no coincide con el guardado: se omiten las coordenadas")
            return None, None
        origin = poly.origin
    else:
        return None, None
    return origin, [from_enu(v, origin) for v in vertices]
