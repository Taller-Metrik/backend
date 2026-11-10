from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.survey import SurveyMode

Point = tuple[float, float]


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    created_at: datetime


class GpsPoint(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    accuracy_m: float = Field(default=5.0, ge=0)
    timestamp_s: float | None = None
    satellites: int | None = Field(
        default=None, ge=0, le=200, description="Satélites usados en la solución (usedInFix), no los visibles (RF-20)"
    )
    cn0_dbhz: float | None = Field(
        default=None, ge=0, le=70, description="C/N0 medio de los 4 satélites usados más fuertes, dB-Hz (RF-20)"
    )
    vertex_id: int | None = Field(
        default=None, ge=0, le=10_000, description="Esquina sobre la que el usuario está quieto (stop-and-go, RF-18)"
    )


class UncertaintyOut(BaseModel):
    """Incertidumbre del área y del perímetro al 95 % (RF-21)."""

    method: Literal["stop_and_go", "continuous"]
    area_sigma_m2: float
    area_u95_m2: float
    area_u95_pct: float
    perimeter_sigma_m: float
    perimeter_u95_m: float
    perimeter_u95_pct: float
    k: float = Field(description="Factor de cobertura: 2 (≈ 95 %); 2,5 si la σ salió solo del error de cierre")
    vertex_sigma_m: list[float] = Field(description="σ por eje de cada vértice")
    closure_m: float | None = Field(description="Error de cierre al volver a fijar la primera esquina (RF-19)")
    closure_consistent: bool | None = Field(
        default=None, description="False si el cierre es mayor de lo esperable: conviene volver a medir"
    )
    origin_latlon: list[float] | None = Field(
        default=None, description="[lat, lon] del origen de las coordenadas locales (x este, y norte) de los vértices"
    )


class CaptureIn(BaseModel):
    """Metadatos de captura enviados por la app (variables del modelo de ML)."""

    odometry: Literal["arcore", "steps"] = "arcore"
    tracking_loss_s: float = Field(default=0.0, ge=0)
    duration_s: float | None = Field(default=None, gt=0)


class SurveyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    mode: SurveyMode = SurveyMode.INTERIOR
    device_model: str | None = Field(default=None, max_length=120)
    points: Annotated[list[Point], Field(max_length=200_000)] = Field(
        default_factory=list, description="Trazo crudo del odómetro (x, y) en metros"
    )
    corners: list[Point] | None = Field(default=None, description="Esquinas marcadas (o vértices del plano importado)")
    gps_points: list[GpsPoint] | None = Field(default=None, description="Lecturas GPS (modo exterior)")
    scale_denominator: int | None = Field(default=None, description="Escala del plano; si no se envía se sugiere")
    capture: CaptureIn | None = Field(default=None, description="Metadatos de captura (modo interior)")
    transport: Literal["walk", "bike", "moto", "car"] = Field(default="walk", description="Cómo se recorrió (modo exterior)")

    @model_validator(mode="after")
    def check_inputs(self) -> "SurveyCreate":
        if self.mode == SurveyMode.EXTERIOR:
            if not self.gps_points or len(self.gps_points) < 3:
                raise ValueError("El modo exterior requiere al menos 3 lecturas GPS")
        elif self.mode == SurveyMode.IMPORTED:
            if not self.corners or len(self.corners) < 3:
                raise ValueError("El modo importado requiere al menos 3 vértices en 'corners'")
        elif len(self.points) < 3 and (not self.corners or len(self.corners) < 3):
            raise ValueError("El modo interior requiere el trazo ('points') o las esquinas ('corners')")
        return self


class SurveyUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class SurveySummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    mode: SurveyMode
    area_m2: float
    perimeter_m: float
    closed: bool
    scale_denominator: int
    created_at: datetime


class SurveyOut(SurveySummary):
    device_model: str | None
    vertices: list[Point]
    wall_lengths_m: list[float]
    interior_angles_deg: list[float]
    closure_error_m: float
    is_simple: bool
    concave_count: int
    uncertainty: UncertaintyOut | None = Field(default=None, description="Solo en recorridos exteriores (GPS)")
