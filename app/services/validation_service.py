"""Persistencia de medidas reales y reportes de margen de error."""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.reference import ReferenceMeasurement
from app.models.survey import Survey
from app.models.user import User
from app.schemas.validation import ReferencesIn
from app.services.geometry import GeometryError
from app.services.project_service import ProjectService, SurveyService
from app.services.validation import ErrorReport, WallComparison, compare_wall, error_report, real_value


class ValidationService:
    def __init__(self, db: AsyncSession, user: User) -> None:
        self.db = db
        self.surveys = SurveyService(db, user)
        self.projects = ProjectService(db, user)

    async def save_references(self, survey_id: int, payload: ReferencesIn) -> Survey:
        """Reemplaza las medidas reales del recorrido."""
        survey = await self.surveys.get(survey_id)
        n_walls = len(survey.wall_lengths_m)
        indices = [w.wall_index for w in payload.walls]
        if len(set(indices)) != len(indices):
            raise GeometryError("Hay muros repetidos en las medidas reales")
        if any(i >= n_walls for i in indices):
            raise GeometryError(f"El recorrido tiene {n_walls} muros (índices 0 a {n_walls - 1})")

        await self.db.execute(delete(ReferenceMeasurement).where(ReferenceMeasurement.survey_id == survey_id))
        for wall in payload.walls:
            real, _ = real_value(wall.readings_m)
            self.db.add(
                ReferenceMeasurement(
                    survey_id=survey_id,
                    wall_index=wall.wall_index,
                    readings_m=wall.readings_m,
                    real_length_m=real,
                    notes=wall.notes,
                )
            )
        survey.real_area_m2 = payload.real_area_m2
        await self.db.commit()
        await self.db.refresh(survey)
        return survey

    async def _comparisons(self, survey: Survey) -> list[WallComparison]:
        refs = (
            await self.db.execute(
                select(ReferenceMeasurement)
                .where(ReferenceMeasurement.survey_id == survey.id)
                .order_by(ReferenceMeasurement.wall_index)
            )
        ).scalars()
        return [compare_wall(r.wall_index, survey.wall_lengths_m[r.wall_index], r.readings_m) for r in refs]

    async def survey_report(self, survey_id: int) -> tuple[Survey, ErrorReport]:
        survey = await self.surveys.get(survey_id)
        report = error_report(
            await self._comparisons(survey), measured_area_m2=survey.area_m2, real_area_m2=survey.real_area_m2
        )
        return survey, report

    async def project_rows(self, project_id: int) -> tuple[list[Survey], list[dict]]:
        project = await self.projects.get(project_id)
        surveys = await self.surveys.list(project_id)
        rows: list[dict] = []
        for survey in sorted(surveys, key=lambda s: s.id):
            for c in await self._comparisons(survey):
                rows.append(
                    {"project": project.name, "survey": survey.name, "mode": survey.mode.value, **c.__dict__}
                )
        return surveys, rows

    async def project_report(self, project_id: int) -> tuple[int, ErrorReport]:
        surveys, rows = await self.project_rows(project_id)
        walls = [WallComparison(**{k: v for k, v in r.items() if k not in ("project", "survey", "mode")}) for r in rows]
        validated = len({r["survey"] for r in rows})
        return validated, error_report(walls)
