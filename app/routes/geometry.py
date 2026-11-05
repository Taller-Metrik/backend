"""Endpoints de cálculo geométrico (sin estado)."""

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, status

from app.schemas.geometry import (
    CalibrateImageIn,
    CalibrateImageOut,
    DistanceIn,
    DistanceOut,
    PolygonAnalysisOut,
    PolygonIn,
    ScaleIn,
    ScaleOut,
    SmoothIn,
    SmoothOut,
)
from app.services import geometry, scale
from app.services.smoothing import smooth_track

router = APIRouter(prefix="/geometry", tags=["Geometría"])


def _bad_request(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))


@router.post("/analyze", response_model=PolygonAnalysisOut)
async def analyze_polygon(payload: PolygonIn) -> PolygonAnalysisOut:
    """Área (Shoelace), perímetro, muros, ángulos interiores y convexidad (RF-06)."""
    try:
        return PolygonAnalysisOut(**asdict(geometry.analyze(payload.vertices)))
    except geometry.GeometryError as exc:
        raise _bad_request(exc) from None


@router.post("/distance", response_model=DistanceOut)
async def distance(payload: DistanceIn) -> DistanceOut:
    """Distancia Euclidiana y Manhattan entre dos puntos (RF-07)."""
    e = geometry.euclidean(payload.a, payload.b)
    m = geometry.manhattan(payload.a, payload.b)
    return DistanceOut(euclidean_m=e, manhattan_m=m, difference_m=m - e)


@router.post("/smooth", response_model=SmoothOut)
async def smooth(payload: SmoothIn) -> SmoothOut:
    """Suaviza el trazo crudo y devuelve el polígono ortogonal con su análisis (RF-05)."""
    try:
        result = smooth_track(
            payload.points,
            corners=payload.corners,
            epsilon=payload.epsilon_m,
            snap_tolerance_deg=payload.snap_tolerance_deg,
            closure_tolerance_m=payload.closure_tolerance_m,
            min_wall_m=payload.min_wall_m,
        )
        analysis = geometry.analyze(result.vertices)
    except geometry.GeometryError as exc:
        raise _bad_request(exc) from None
    return SmoothOut(**asdict(result), analysis=PolygonAnalysisOut(**asdict(analysis)))


@router.post("/scale", response_model=ScaleOut)
async def to_scale(payload: ScaleIn) -> ScaleOut:
    """Convierte longitudes reales a milímetros en el papel (RF-10)."""
    try:
        paper = [scale.to_paper_mm(length, payload.denominator) for length in payload.lengths_m]
    except geometry.GeometryError as exc:
        raise _bad_request(exc) from None
    return ScaleOut(scale=f"1:{payload.denominator}", lengths_m=payload.lengths_m, paper_mm=paper)


@router.post("/calibrate-image", response_model=CalibrateImageOut)
async def calibrate_image(payload: CalibrateImageIn) -> CalibrateImageOut:
    """Calibra un plano importado con una distancia conocida y mide sobre él (RF-11)."""
    try:
        mpp = scale.meters_per_pixel(payload.p1_px, payload.p2_px, payload.real_distance_m)
        points_m = scale.pixels_to_meters(payload.points_px, mpp)
        analysis = (
            PolygonAnalysisOut(**asdict(geometry.analyze(points_m))) if len(points_m) >= 3 else None
        )
    except geometry.GeometryError as exc:
        raise _bad_request(exc) from None
    return CalibrateImageOut(meters_per_pixel=mpp, points_m=points_m, analysis=analysis)
