"""Esquemas del metrado de acabados con presupuesto (CU-07)."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.schemas.fence import BudgetOut, TakeoffItemOut

Price = Annotated[float, Field(ge=0, le=1_000_000)]
LaborKey = Literal["floor_m2", "baseboard_m", "plaster_m2", "wall_paint_m2", "ceiling_paint_m2"]


class OpeningIn(BaseModel):
    wall: int = Field(ge=0, le=10_000, description="Muro del vano (0 = del vértice 1 al 2)")
    kind: Literal["door", "window"]
    width_m: float = Field(gt=0, le=10)
    height_m: float = Field(gt=0, le=6)


class FinishesIn(BaseModel):
    height_m: float = Field(default=2.50, ge=1.8, le=6.0, description="Altura del piso al techo")
    openings: list[OpeningIn] = Field(default_factory=list, max_length=50)
    labor_prices: dict[LaborKey, Price] | None = Field(
        default=None, description="Precio de mano de obra por m² o m (S/); los insumos toman el precio del catálogo"
    )
    use_catalog: bool = Field(default=True, description="Usar el catálogo de precios (tienda o propio) para los insumos")
    overhead_pct: float = Field(default=10.0, ge=0, le=50)
    profit_pct: float = Field(default=5.0, ge=0, le=50)


class FinishesOut(BaseModel):
    survey_id: int
    area_m2: float
    perimeter_m: float
    height_m: float
    items: list[TakeoffItemOut]
    assumptions: list[str]
    notes: list[str]
    budget: BudgetOut | None
    price_sources: dict[str, str] = Field(description="Origen del precio de cada partida presupuestada: user | store | input")
