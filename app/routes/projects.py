"""Proyectos y recorridos (CU-01, CU-02, CU-03)."""

from fastapi import APIRouter, HTTPException, Response, status

from app.core.deps import CurrentUserDep, DbDep
from app.schemas.project import ProjectCreate, ProjectOut, ProjectUpdate, SurveyCreate, SurveyOut, SurveySummary
from app.services.geometry import GeometryError
from app.services.project_service import NotFoundError, ProjectService, SurveyService

router = APIRouter(tags=["Proyectos y recorridos"])

_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recurso no encontrado")


@router.post("/projects", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create_project(payload: ProjectCreate, db: DbDep, user: CurrentUserDep) -> ProjectOut:
    return ProjectOut.model_validate(await ProjectService(db, user).create(payload))


@router.get("/projects", response_model=list[ProjectOut])
async def list_projects(db: DbDep, user: CurrentUserDep) -> list[ProjectOut]:
    return [ProjectOut.model_validate(p) for p in await ProjectService(db, user).list()]


@router.get("/projects/{project_id}", response_model=ProjectOut)
async def get_project(project_id: int, db: DbDep, user: CurrentUserDep) -> ProjectOut:
    try:
        return ProjectOut.model_validate(await ProjectService(db, user).get(project_id))
    except NotFoundError:
        raise _NOT_FOUND from None


@router.patch("/projects/{project_id}", response_model=ProjectOut)
async def update_project(project_id: int, payload: ProjectUpdate, db: DbDep, user: CurrentUserDep) -> ProjectOut:
    try:
        return ProjectOut.model_validate(await ProjectService(db, user).update(project_id, payload))
    except NotFoundError:
        raise _NOT_FOUND from None


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project_id: int, db: DbDep, user: CurrentUserDep) -> Response:
    try:
        await ProjectService(db, user).delete(project_id)
    except NotFoundError:
        raise _NOT_FOUND from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/projects/{project_id}/surveys", response_model=SurveyOut, status_code=status.HTTP_201_CREATED)
async def create_survey(project_id: int, payload: SurveyCreate, db: DbDep, user: CurrentUserDep) -> SurveyOut:
    """Procesa un recorrido: suaviza el trazo, calcula el plano y lo guarda."""
    try:
        survey = await SurveyService(db, user).create(project_id, payload)
    except NotFoundError:
        raise _NOT_FOUND from None
    except GeometryError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from None
    return SurveyOut.model_validate(survey)


@router.get("/projects/{project_id}/surveys", response_model=list[SurveySummary])
async def list_surveys(project_id: int, db: DbDep, user: CurrentUserDep) -> list[SurveySummary]:
    try:
        return [SurveySummary.model_validate(s) for s in await SurveyService(db, user).list(project_id)]
    except NotFoundError:
        raise _NOT_FOUND from None


@router.get("/surveys/{survey_id}", response_model=SurveyOut)
async def get_survey(survey_id: int, db: DbDep, user: CurrentUserDep) -> SurveyOut:
    try:
        return SurveyOut.model_validate(await SurveyService(db, user).get(survey_id))
    except NotFoundError:
        raise _NOT_FOUND from None


@router.delete("/surveys/{survey_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_survey(survey_id: int, db: DbDep, user: CurrentUserDep) -> Response:
    try:
        await SurveyService(db, user).delete(survey_id)
    except NotFoundError:
        raise _NOT_FOUND from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
