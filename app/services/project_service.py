"""Proyectos y recorridos: persistencia y procesamiento."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.project import Project
from app.models.survey import Survey, SurveyMode
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectUpdate, SurveyCreate
from app.services import geometry, scale
from app.services.gps import GpsPolygon, GpsReading, gps_polygon, uncertainty_report
from app.services.smoothing import smooth_track


class NotFoundError(Exception):
    """El recurso no existe o no pertenece al usuario."""


class ProjectService:
    def __init__(self, db: AsyncSession, user: User) -> None:
        self.db = db
        self.user = user

    async def create(self, payload: ProjectCreate) -> Project:
        project = Project(owner_id=self.user.id, name=payload.name.strip(), description=payload.description)
        self.db.add(project)
        await self.db.commit()
        await self.db.refresh(project)
        return project

    async def list(self) -> list[Project]:
        result = await self.db.execute(
            select(Project).where(Project.owner_id == self.user.id).order_by(Project.created_at.desc(), Project.id.desc())
        )
        return list(result.scalars())

    async def get(self, project_id: int) -> Project:
        project = await self.db.get(Project, project_id)
        if project is None or project.owner_id != self.user.id:
            raise NotFoundError
        return project

    async def update(self, project_id: int, payload: ProjectUpdate) -> Project:
        project = await self.get(project_id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(project, field, value)
        await self.db.commit()
        await self.db.refresh(project)
        return project

    async def delete(self, project_id: int) -> None:
        project = await self.get(project_id)
        await self.db.delete(project)
        await self.db.commit()


class SurveyService:
    def __init__(self, db: AsyncSession, user: User) -> None:
        self.db = db
        self.user = user
        self.projects = ProjectService(db, user)

    async def create(self, project_id: int, payload: SurveyCreate) -> Survey:
        """Procesa el recorrido (suavizado + análisis) y lo guarda."""
        await self.projects.get(project_id)
        processed = self._process(payload)
        survey = Survey(project_id=project_id, name=payload.name.strip(), mode=payload.mode,
                        device_model=payload.device_model, **processed)
        self.db.add(survey)
        await self.db.commit()
        await self.db.refresh(survey)
        return survey

    def _process(self, payload: SurveyCreate) -> dict:
        closed, closure_error, snapped, total = True, 0.0, 0, 0
        uncertainty: dict | None = None
        if payload.mode == SurveyMode.INTERIOR:
            smoothed = smooth_track(
                payload.points,
                corners=payload.corners,
                epsilon=settings.rdp_epsilon_m,
                snap_tolerance_deg=settings.snap_tolerance_deg,
                closure_tolerance_m=settings.closure_tolerance_m,
            )
            vertices, closed, closure_error = smoothed.vertices, smoothed.closed, smoothed.closure_error_m
            snapped, total = smoothed.snapped_edges, smoothed.total_edges
        elif payload.mode == SurveyMode.IMPORTED:
            vertices = geometry.normalize_polygon(payload.corners or [])
        else:
            # El cierre GPS va solo dentro de `uncertainty`: `closure_error_m` es una variable del modelo de ML
            poly = self._process_exterior(payload)
            vertices, uncertainty = poly.vertices, uncertainty_report(poly)

        analysis = geometry.analyze(vertices)
        xs, ys = [v[0] for v in analysis.vertices], [v[1] for v in analysis.vertices]
        denominator = payload.scale_denominator or scale.suggest_scale(max(xs) - min(xs), max(ys) - min(ys))
        scale.validate_scale(denominator)

        return {
            "raw_points": [list(p) for p in payload.points],
            "corners": [list(p) for p in payload.corners] if payload.corners else None,
            "gps_points": [g.model_dump() for g in payload.gps_points] if payload.gps_points else None,
            "vertices": [list(v) for v in analysis.vertices],
            "wall_lengths_m": analysis.wall_lengths_m,
            "interior_angles_deg": analysis.interior_angles_deg,
            "area_m2": analysis.area_m2,
            "perimeter_m": analysis.perimeter_m,
            "closure_error_m": closure_error,
            "closed": closed,
            "is_simple": analysis.is_simple,
            "concave_count": len(analysis.concave_vertices),
            "scale_denominator": denominator,
            "snapped_edges": snapped,
            "total_edges": total,
            "capture": self._capture(payload),
            "uncertainty": uncertainty,
        }

    @staticmethod
    def _capture(payload: SurveyCreate) -> dict | None:
        """Metadatos de captura. En exterior siempre se guarda el transporte (lo usan el informe y la validación)."""
        capture = payload.capture.model_dump() if payload.capture else None
        if payload.mode == SurveyMode.EXTERIOR:
            capture = {**(capture or {}), "transport": payload.transport}
        return capture

    def _process_exterior(self, payload: SurveyCreate) -> GpsPolygon:
        readings = [GpsReading(**g.model_dump()) for g in payload.gps_points or []]
        return gps_polygon(readings, transport=payload.transport)

    async def list(self, project_id: int) -> list[Survey]:
        await self.projects.get(project_id)
        result = await self.db.execute(
            select(Survey).where(Survey.project_id == project_id).order_by(Survey.created_at.desc(), Survey.id.desc())
        )
        return list(result.scalars())

    async def get(self, survey_id: int) -> Survey:
        survey = await self.db.get(Survey, survey_id)
        if survey is None:
            raise NotFoundError
        await self.projects.get(survey.project_id)  # verifica propiedad
        return survey

    async def rename(self, survey_id: int, name: str) -> Survey:
        survey = await self.get(survey_id)
        survey.name = name.strip()
        await self.db.commit()
        await self.db.refresh(survey)
        return survey

    async def delete(self, survey_id: int) -> None:
        survey = await self.get(survey_id)
        await self.db.delete(survey)
        await self.db.commit()
