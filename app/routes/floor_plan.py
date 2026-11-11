"""Plano de vivienda con varios ambientes (CU-08, RF-25, RF-26)."""

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Response, status

from app.core.deps import CurrentUserDep, DbDep
from app.models.survey import SurveyMode
from app.schemas.floor_plan import FloorPlanIn, FloorPlanOut
from app.services.floor_plan import FloorPlan, Join, Room, build_floor_plan, floor_plan_dxf
from app.services.geometry import GeometryError
from app.services.project_service import NotFoundError, ProjectService, SurveyService

router = APIRouter(tags=["Plano de vivienda"])


def _unprocessable(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail)


async def _plan(project_id: int, payload: FloorPlanIn, db: DbDep, user: CurrentUserDep) -> tuple[str, FloorPlan]:
    try:
        project = await ProjectService(db, user).get(project_id)
        surveys = {s.id: s for s in await SurveyService(db, user).list(project_id)}
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recurso no encontrado") from None
    if len(set(payload.rooms)) != len(payload.rooms):
        raise _unprocessable("Un ambiente aparece dos veces en el plano")
    rooms = []
    for sid in payload.rooms:
        s = surveys.get(sid)
        if s is None:
            raise _unprocessable(f"El recorrido {sid} no pertenece a este proyecto")
        if s.mode == SurveyMode.EXTERIOR:
            raise _unprocessable(f"«{s.name}» es un terreno: el plano de vivienda une ambientes interiores")
        rooms.append(Room(sid, s.name, [(float(v[0]), float(v[1])) for v in s.vertices or []]))
    try:
        plan = build_floor_plan(rooms, [
            Join(j.a_survey, j.a_wall, j.b_survey, j.b_wall, j.thickness_m, a_point=j.a_point, b_point=j.b_point)
            for j in payload.joins
        ])
    except GeometryError as exc:
        raise _unprocessable(str(exc)) from None
    return project.name, plan


@router.post("/projects/{project_id}/floor-plan", response_model=FloorPlanOut)
async def floor_plan(project_id: int, payload: FloorPlanIn, db: DbDep, user: CurrentUserDep) -> FloorPlanOut:
    """Une los ambientes del proyecto por sus muros compartidos: posiciones, cuadro de áreas y advertencias."""
    _, plan = await _plan(project_id, payload, db, user)
    return FloorPlanOut(project_id=project_id, **asdict(plan))


@router.post(
    "/projects/{project_id}/floor-plan.dxf",
    response_class=Response,
    responses={200: {"content": {"application/dxf": {}}, "description": "DXF de la planta completa"}},
)
async def floor_plan_dxf_file(project_id: int, payload: FloorPlanIn, db: DbDep, user: CurrentUserDep) -> Response:
    """DXF de la vivienda: un polígono por ambiente con su nombre y área, y el cuadro de áreas."""
    name, plan = await _plan(project_id, payload, db, user)
    try:
        content = floor_plan_dxf(plan, name, payload.scale_denominator)
    except GeometryError as exc:
        raise _unprocessable(str(exc)) from None
    return Response(
        content=content.encode("utf-8"),
        media_type="application/dxf",
        headers={"Content-Disposition": f'attachment; filename="metrik_vivienda_{project_id}.dxf"'},
    )
