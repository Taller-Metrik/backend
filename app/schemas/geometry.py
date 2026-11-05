from typing import Annotated

from pydantic import BaseModel, Field

Point = tuple[float, float]
Polygon = Annotated[list[Point], Field(min_length=3, max_length=10_000)]


class PolygonIn(BaseModel):
    vertices: Polygon


class PolygonAnalysisOut(BaseModel):
    vertices: list[Point]
    area_m2: float
    perimeter_m: float
    wall_lengths_m: list[float]
    interior_angles_deg: list[float]
    concave_vertices: list[int]
    is_convex: bool
    is_simple: bool
    orientation: str
    angle_sum_deg: float
    expected_angle_sum_deg: float


class DistanceIn(BaseModel):
    a: Point
    b: Point


class DistanceOut(BaseModel):
    euclidean_m: float
    manhattan_m: float
    difference_m: float


class SmoothIn(BaseModel):
    points: Annotated[list[Point], Field(min_length=3, max_length=200_000)] = Field(
        description="Trazo crudo del recorrido (x, y) en metros"
    )
    corners: list[Point] | None = Field(default=None, description="Esquinas marcadas por el usuario (opcional)")
    epsilon_m: float = Field(default=0.10, gt=0, le=2)
    snap_tolerance_deg: float = Field(default=15.0, ge=0, le=45)
    closure_tolerance_m: float = Field(default=1.0, gt=0, le=20)
    min_wall_m: float = Field(default=0.30, ge=0, le=5)


class SmoothOut(BaseModel):
    vertices: list[Point]
    input_points: int
    simplified_points: int
    closed: bool
    closure_error_m: float
    dominant_angle_deg: float
    snapped_edges: int
    total_edges: int
    analysis: PolygonAnalysisOut


class ScaleIn(BaseModel):
    lengths_m: Annotated[list[float], Field(min_length=1)]
    denominator: int = Field(description="Denominador de la escala: 100 para 1:100")


class ScaleOut(BaseModel):
    scale: str
    lengths_m: list[float]
    paper_mm: list[float]


class CalibrateImageIn(BaseModel):
    p1_px: Point
    p2_px: Point
    real_distance_m: float = Field(gt=0)
    points_px: list[Point] = Field(default_factory=list, description="Vértices a medir sobre la imagen")


class CalibrateImageOut(BaseModel):
    meters_per_pixel: float
    points_m: list[Point]
    analysis: PolygonAnalysisOut | None = None
