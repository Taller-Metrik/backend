"""Arma los datos del informe técnico (CU-10) a partir de un recorrido guardado."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.survey import Survey, SurveyMode
from app.models.user import User
from app.services.geometry import GeometryError
from app.services.gps import GpsReading, gps_polygon
from app.services.gps_core import from_enu
from app.services.project_service import ProjectService, SurveyService
from app.services.report_pdf import ReportData, ReportValidation, render_pdf
from app.services.validation_service import ValidationService


class ReportService:
    def __init__(self, db: AsyncSession, user: User) -> None:
        self.db = db
        self.user = user

    async def data(self, survey_id: int) -> ReportData:
        """Datos del informe. Lanza NotFoundError si el recorrido no existe o es de otro usuario."""
        survey = await SurveyService(self.db, self.user).get(survey_id)
        project = await ProjectService(self.db, self.user).get(survey.project_id)
        capture = survey.capture or {}
        origin, vertices_latlon = self._coordinates(survey, capture.get("transport") or "walk")
        return ReportData(
            project_name=project.name,
            survey_name=survey.name,
            mode=survey.mode.value,
            odometry=capture.get("odometry"),
            transport=capture.get("transport"),
            device_model=survey.device_model,
            created_at=survey.measured_at or survey.created_at,
            vertices=[(float(v[0]), float(v[1])) for v in survey.vertices],
            wall_lengths_m=list(survey.wall_lengths_m),
            interior_angles_deg=list(survey.interior_angles_deg),
            area_m2=survey.area_m2,
            perimeter_m=survey.perimeter_m,
            closure_error_m=survey.closure_error_m,
            scale_denominator=survey.scale_denominator,
            uncertainty=survey.uncertainty,
            validation=await self._validation(survey_id),
            origin_latlon=origin,
            vertices_latlon=vertices_latlon,
        )

    async def pdf(self, survey_id: int) -> bytes:
        return render_pdf(await self.data(survey_id))

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

    @staticmethod
    def _coordinates(
        survey: Survey, transport: str
    ) -> tuple[tuple[float, float] | None, list[tuple[float, float]] | None]:
        """Origen y latitud/longitud de los vértices de un recorrido GPS.

        Los vértices se guardan en metros respecto del origen del polígono (primera lectura válida), que se
        vuelve a obtener con el mismo procesamiento con el que se creó el recorrido.
        """
        if survey.mode != SurveyMode.EXTERIOR or not survey.gps_points:
            return None, None
        try:
            readings = [GpsReading(**p) for p in survey.gps_points]
            origin = gps_polygon(readings, transport=transport).origin
        except (GeometryError, TypeError):
            return None, None
        return origin, [from_enu((float(v[0]), float(v[1])), origin) for v in survey.vertices]
