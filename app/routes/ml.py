"""Machine Learning: corrección de medidas y confiabilidad del recorrido (RF-15)."""

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.core.deps import CurrentUserDep, DbDep
from app.services import ml_service
from app.services.project_service import NotFoundError, SurveyService

router = APIRouter(tags=["Machine Learning"])


class WallCorrectionOut(BaseModel):
    wall_index: int
    measured_m: float
    corrected_m: float
    correction_m: float


class MlAnalysisOut(BaseModel):
    survey_id: int
    reliability_probability: float
    reliable: bool
    recommendation: str
    walls: list[WallCorrectionOut]
    corrected_perimeter_m: float
    corrector_model: str
    classifier_model: str
    version: str


_UNAVAILABLE = status.HTTP_503_SERVICE_UNAVAILABLE


@router.get("/ml/info")
async def info() -> dict[str, Any]:
    """Modelos cargados y sus métricas en el conjunto de prueba."""
    try:
        return ml_service.models_info()
    except ml_service.ModelsNotAvailableError as exc:
        raise HTTPException(status_code=_UNAVAILABLE, detail=str(exc)) from None


@router.get("/surveys/{survey_id}/ml", response_model=MlAnalysisOut)
async def analyze(survey_id: int, db: DbDep, user: CurrentUserDep) -> MlAnalysisOut:
    """Corrige las longitudes de los muros y estima si el recorrido es confiable."""
    try:
        survey = await SurveyService(db, user).get(survey_id)
        result = ml_service.analyze_survey(survey)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recurso no encontrado") from None
    except ml_service.NotApplicableError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None
    except ml_service.ModelsNotAvailableError as exc:
        raise HTTPException(status_code=_UNAVAILABLE, detail=str(exc)) from None
    return MlAnalysisOut(survey_id=survey_id, **asdict(result))
