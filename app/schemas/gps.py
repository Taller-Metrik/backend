from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.geometry import PolygonAnalysisOut
from app.schemas.project import GpsPoint, UncertaintyOut


class LatLon(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class GpsErrorIn(BaseModel):
    readings: list[GpsPoint] = Field(min_length=2, description="Lecturas estáticas en un mismo punto")
    reference: LatLon | None = Field(default=None, description="Punto real conocido; si no, se usa la media")
    calibration_threshold_m: float = Field(default=8.0, gt=0)


class GpsErrorOut(BaseModel):
    n: int
    reference: LatLon
    reference_is_mean: bool
    mean_error_m: float
    cep50_m: float
    r95_m: float
    drms_m: float
    two_drms_m: float
    max_error_m: float
    needs_calibration: bool
    recommendation: str


class GpsAreaIn(BaseModel):
    points: list[GpsPoint] = Field(min_length=3)
    max_accuracy_m: float = Field(default=10.0, gt=0)
    simplify_epsilon_m: float | None = Field(default=None, gt=0, description="Por defecto 2 × precisión mediana")
    use_kalman: bool = True
    scale_denominator: int = Field(default=500)
    transport: Literal["walk", "bike", "moto", "car"] = Field(default="walk", description="Cómo se recorrió el terreno")


class GpsAreaOut(BaseModel):
    origin: LatLon
    used_readings: int
    discarded_readings: int
    discarded_by_signal: int = Field(description="Lecturas descartadas por pocos satélites o señal débil (RF-20)")
    scale: str
    analysis: PolygonAnalysisOut
    uncertainty: UncertaintyOut


class HaversineIn(BaseModel):
    a: LatLon
    b: LatLon


class HaversineOut(BaseModel):
    distance_m: float
