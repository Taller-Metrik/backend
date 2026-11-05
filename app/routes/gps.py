"""Modo exterior: GPS (RF-08, RF-09)."""

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, status

from app.schemas.geometry import PolygonAnalysisOut
from app.schemas.gps import GpsAreaIn, GpsAreaOut, GpsErrorIn, GpsErrorOut, HaversineIn, HaversineOut, LatLon
from app.services import geometry, gps, scale

router = APIRouter(prefix="/gps", tags=["GPS (modo exterior)"])


def _readings(points) -> list[gps.GpsReading]:
    return [gps.GpsReading(**p.model_dump()) for p in points]


@router.post("/error", response_model=GpsErrorOut)
async def gps_error(payload: GpsErrorIn) -> GpsErrorOut:
    """Margen de error del GPS con lecturas estáticas y decisión de calibración (RF-09)."""
    try:
        ref = (payload.reference.lat, payload.reference.lon) if payload.reference else None
        m = gps.error_metrics(_readings(payload.readings), ref, payload.calibration_threshold_m)
    except geometry.GeometryError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from None
    recommendation = (
        "Error inicial alto: permanecer quieto 30 s para calibrar antes de medir"
        if m.needs_calibration
        else "Precisión suficiente: se puede usar la última ubicación conocida sin calibrar"
    )
    data = asdict(m)
    data["reference"] = LatLon(lat=m.reference[0], lon=m.reference[1])
    return GpsErrorOut(**data, recommendation=recommendation)


@router.post("/area", response_model=GpsAreaOut)
async def gps_area(payload: GpsAreaIn) -> GpsAreaOut:
    """Área y perímetro de un terreno recorrido con GPS (RF-08)."""
    try:
        scale.validate_scale(payload.scale_denominator)
        poly = gps.gps_polygon(
            _readings(payload.points),
            max_accuracy_m=payload.max_accuracy_m,
            simplify_epsilon_m=payload.simplify_epsilon_m,
            use_kalman=payload.use_kalman,
        )
        analysis = geometry.analyze(poly.vertices)
    except geometry.GeometryError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from None
    return GpsAreaOut(
        origin=LatLon(lat=poly.origin[0], lon=poly.origin[1]),
        used_readings=poly.used_readings,
        discarded_readings=poly.discarded_readings,
        scale=f"1:{payload.scale_denominator}",
        analysis=PolygonAnalysisOut(**asdict(analysis)),
    )


@router.post("/distance", response_model=HaversineOut)
async def gps_distance(payload: HaversineIn) -> HaversineOut:
    """Distancia geodésica entre dos coordenadas (Haversine)."""
    return HaversineOut(distance_m=gps.haversine((payload.a.lat, payload.a.lon), (payload.b.lat, payload.b.lon)))
