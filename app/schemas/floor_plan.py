"""Esquemas del plano de vivienda con varios ambientes (CU-08)."""

from pydantic import BaseModel, Field


class JoinIn(BaseModel):
    a_survey: int = Field(description="Ambiente ya ubicado (o la base)")
    a_wall: int | None = Field(default=None, ge=0, le=10_000, description="Muro de A (0 = del vértice 1 al 2)")
    a_point: tuple[float, float] | None = Field(
        default=None, description="Puerta en las coordenadas de A: se usa el muro más cercano y se alinea la puerta"
    )
    b_survey: int
    b_wall: int | None = Field(default=None, ge=0, le=10_000)
    b_point: tuple[float, float] | None = None
    thickness_m: float = Field(default=0.15, gt=0, le=0.5, description="Espesor del muro compartido (0,15 tabique; 0,25 portante)")


class FloorPlanIn(BaseModel):
    rooms: list[int] = Field(min_length=1, max_length=50, description="Recorridos del proyecto; el primero es la base")
    joins: list[JoinIn] = Field(default_factory=list, max_length=100)
    scale_denominator: int = Field(default=100, description="Escala del DXF")


class PlacedRoomOut(BaseModel):
    survey_id: int
    name: str
    vertices: list[tuple[float, float]]
    area_m2: float


class FloorPlanOut(BaseModel):
    project_id: int
    rooms: list[PlacedRoomOut]
    total_area_m2: float
    warnings: list[str]
