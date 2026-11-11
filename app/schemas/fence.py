"""Esquemas del metrado y presupuesto de cerco perimétrico (CU-09)."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field

Price = Annotated[float, Field(ge=0, le=1_000_000)]
PriceKey = Annotated[str, Field(min_length=1, max_length=40)]


class GateIn(BaseModel):
    side: int = Field(ge=0, le=10_000, description="Lado donde va el portón (0 = del vértice 1 al 2)")
    width_m: float = Field(gt=0, le=50)


class FenceIn(BaseModel):
    kind: Literal["wire", "brick"] = Field(description="wire = postes con alambre de púas; brick = muro de ladrillo")
    gates: list[GateIn] = Field(default_factory=list, max_length=50)
    post_spacing_m: float = Field(default=3.0, ge=1.5, le=5.0, description="Separación de postes (alambre)")
    strands: int = Field(default=4, ge=1, le=10, description="Hilos de alambre")
    wall_height_m: float = Field(default=2.40, ge=1.0, le=4.0, description="Altura del muro (ladrillo)")
    column_spacing_m: float = Field(default=3.0, ge=2.0, le=4.5, description="Separación de columnas (ladrillo)")
    prices: dict[PriceKey, Price] | None = Field(
        default=None, max_length=40,
        description="Precio unitario (S/) por clave de partida presupuestable; sin precios no se arma presupuesto",
    )
    overhead_pct: float = Field(default=10.0, ge=0, le=50, description="Gastos generales (%)")
    profit_pct: float = Field(default=5.0, ge=0, le=50, description="Utilidad (%)")
    use_catalog: bool = Field(
        default=True, description="Completar con el catálogo (tienda o precio propio) las partidas sin precio escrito"
    )


class TakeoffItemOut(BaseModel):
    key: str
    description: str
    unit: str
    quantity: float
    min: float
    max: float
    purchase: float
    priceable: bool = Field(description="False = desglose informativo, no entra al presupuesto")


class BudgetLineOut(BaseModel):
    key: str
    description: str
    unit: str
    quantity: float
    unit_price: float
    subtotal: float


class BudgetOut(BaseModel):
    lines: list[BudgetLineOut]
    direct_cost: float
    overhead_pct: float
    overhead: float
    profit_pct: float
    profit: float
    subtotal: float
    igv_pct: float
    igv: float
    total: float
    missing_prices: list[str]
    currency: str


class FenceOut(BaseModel):
    survey_id: int
    kind: str
    perimeter_m: float
    perimeter_u95_m: float | None
    net_length_m: float
    items: list[TakeoffItemOut]
    assumptions: list[str]
    notes: list[str]
    budget: BudgetOut | None
    price_sources: dict[str, str] = Field(default_factory=dict, description="Origen de cada precio: store, user o input")
