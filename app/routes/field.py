"""Validación GPS por referencia y calibraciones de sensores."""

from dataclasses import asdict
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.core.deps import CurrentUserDep, DbDep
from app.models.field_data import SensorCalibration
from app.models.survey import SurveyMode
from app.services.geometry import GeometryError
from app.services.gps_reference import evaluate
from app.services.project_service import NotFoundError, SurveyService

router = APIRouter(tags=["Validación GPS y calibración"])


class LatLonIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class GpsReferenceIn(BaseModel):
    reference_type: Literal["cancha", "catastro", "satelital", "tramo_base", "rtk"]
    real_area_m2: float | None = Field(default=None, gt=0)
    real_perimeter_m: float | None = Field(default=None, gt=0)
    vertices: list[LatLonIn] | None = Field(default=None, description="Esquinas reales (lat, lon), opcional")


class GpsReferenceOut(BaseModel):
    survey_id: int
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


_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recurso no encontrado")


async def _report(db, user, survey_id: int, payload: GpsReferenceIn | None) -> GpsReferenceOut:
    survey = await SurveyService(db, user).get(survey_id)
    if survey.mode != SurveyMode.EXTERIOR:
        raise HTTPException(status_code=409, detail="La referencia GPS aplica a recorridos exteriores; para interiores use la wincha")
    if payload is not None:
        if payload.real_area_m2 is None and payload.real_perimeter_m is None and not payload.vertices:
            raise HTTPException(status_code=422, detail="Indique el área real, el perímetro real o las esquinas de la referencia")
        survey.reference_type = payload.reference_type
        survey.real_area_m2 = payload.real_area_m2
        survey.real_perimeter_m = payload.real_perimeter_m
        survey.reference_vertices = [v.model_dump() for v in payload.vertices] if payload.vertices else None
    elif survey.reference_type is None:
        raise HTTPException(status_code=409, detail="El recorrido aún no tiene referencia")
    try:
        rep = evaluate(
            reference_type=survey.reference_type,
            measured_vertices=[tuple(v) for v in survey.vertices],
            gps_points=survey.gps_points or [],
            transport=(survey.capture or {}).get("transport", "walk"),
            real_area_m2=survey.real_area_m2,
            real_perimeter_m=survey.real_perimeter_m,
            reference_vertices=survey.reference_vertices,
        )
    except GeometryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    if payload is not None:
        survey.real_area_m2 = rep.real_area_m2
        survey.real_perimeter_m = rep.real_perimeter_m
        await db.commit()
    return GpsReferenceOut(survey_id=survey_id, **asdict(rep))


@router.put("/surveys/{survey_id}/gps-reference", response_model=GpsReferenceOut)
async def save_gps_reference(survey_id: int, payload: GpsReferenceIn, db: DbDep, user: CurrentUserDep) -> GpsReferenceOut:
    """Registra la referencia real de un terreno medido con GPS y devuelve el margen de error."""
    try:
        return await _report(db, user, survey_id, payload)
    except NotFoundError:
        raise _NOT_FOUND from None


@router.get("/surveys/{survey_id}/gps-reference", response_model=GpsReferenceOut)
async def get_gps_reference(survey_id: int, db: DbDep, user: CurrentUserDep) -> GpsReferenceOut:
    try:
        return await _report(db, user, survey_id, None)
    except NotFoundError:
        raise _NOT_FOUND from None


class CalibrationIn(BaseModel):
    kind: Literal["step_length", "gyro_drift", "gps_static"]
    device_id: str | None = Field(default=None, max_length=80)
    params: dict[str, Any]


class CalibrationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    device_id: str | None
    origin: str | None
    params: dict[str, Any]
    created_at: datetime


@router.post("/calibrations", response_model=CalibrationOut, status_code=status.HTTP_201_CREATED)
async def save_calibration(payload: CalibrationIn, db: DbDep, user: CurrentUserDep) -> CalibrationOut:
    """Guarda una calibración hecha en la app (largo de paso, deriva del giroscopio, precisión GPS)."""
    cal = SensorCalibration(owner_id=user.id, device_id=payload.device_id, kind=payload.kind, origin="app", params=payload.params)
    db.add(cal)
    await db.commit()
    await db.refresh(cal)
    return CalibrationOut.model_validate(cal)


@router.get("/calibrations", response_model=list[CalibrationOut])
async def list_calibrations(db: DbDep, user: CurrentUserDep, kind: str | None = None) -> list[CalibrationOut]:
    q = select(SensorCalibration).where(SensorCalibration.owner_id == user.id)
    if kind:
        q = q.where(SensorCalibration.kind == kind)
    rows = (await db.execute(q.order_by(SensorCalibration.created_at.desc(), SensorCalibration.id.desc()).limit(50))).scalars()
    return [CalibrationOut.model_validate(r) for r in rows]
