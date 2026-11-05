"""Validación de medidas: app vs wincha (RF-13, RF-14)."""

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Response, status

from app.core.deps import CurrentUserDep, DbDep
from app.schemas.validation import ErrorReportOut, ProjectValidationOut, ReferencesIn, SurveyValidationOut
from app.services.geometry import GeometryError
from app.services.project_service import NotFoundError
from app.services.validation import to_csv
from app.services.validation_service import ValidationService

router = APIRouter(tags=["Validación (margen de error)"])

_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recurso no encontrado")


def _warnings(report) -> list[str]:
    return [
        f"Muro {w.wall_index + 1}: las lecturas de wincha difieren más de 1 cm; tome una tercera lectura"
        for w in report.walls
        if w.needs_extra_reading
    ]


@router.put("/surveys/{survey_id}/references", response_model=SurveyValidationOut)
async def save_references(survey_id: int, payload: ReferencesIn, db: DbDep, user: CurrentUserDep) -> SurveyValidationOut:
    """Registra (reemplaza) las medidas reales con wincha de los muros del recorrido y devuelve el error."""
    service = ValidationService(db, user)
    try:
        await service.save_references(survey_id, payload)
        survey, report = await service.survey_report(survey_id)
    except NotFoundError:
        raise _NOT_FOUND from None
    except GeometryError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from None
    return SurveyValidationOut(
        survey_id=survey.id, survey_name=survey.name, report=ErrorReportOut(**asdict(report)), warnings=_warnings(report)
    )


@router.get("/surveys/{survey_id}/validation", response_model=SurveyValidationOut)
async def survey_validation(survey_id: int, db: DbDep, user: CurrentUserDep) -> SurveyValidationOut:
    try:
        survey, report = await ValidationService(db, user).survey_report(survey_id)
    except NotFoundError:
        raise _NOT_FOUND from None
    except GeometryError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None
    return SurveyValidationOut(
        survey_id=survey.id, survey_name=survey.name, report=ErrorReportOut(**asdict(report)), warnings=_warnings(report)
    )


@router.get("/projects/{project_id}/validation", response_model=ProjectValidationOut)
async def project_validation(project_id: int, db: DbDep, user: CurrentUserDep) -> ProjectValidationOut:
    """Margen de error global del proyecto (todos los muros con medida real)."""
    try:
        validated, report = await ValidationService(db, user).project_report(project_id)
    except NotFoundError:
        raise _NOT_FOUND from None
    except GeometryError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None
    return ProjectValidationOut(project_id=project_id, surveys_validated=validated, report=ErrorReportOut(**asdict(report)))


@router.get(
    "/projects/{project_id}/validation.csv",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}, "description": "Planilla de validación"}},
)
async def project_validation_csv(project_id: int, db: DbDep, user: CurrentUserDep) -> Response:
    """Planilla de validación (sección 6 del protocolo) para abrir en Excel."""
    try:
        _, rows = await ValidationService(db, user).project_rows(project_id)
    except NotFoundError:
        raise _NOT_FOUND from None
    return Response(
        content=to_csv(rows).encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="metrik_validacion_proyecto_{project_id}.csv"'},
    )
