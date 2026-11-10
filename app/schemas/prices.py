"""Esquemas del catálogo de precios (RF-23)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class PriceOut(BaseModel):
    key: str
    description: str
    unit: str = Field(description="Unidad de venta (bolsa, galón, caja…)")
    content: float = Field(description="Contenido de la unidad de venta")
    content_unit: str
    price: float | None = Field(description="Precio que se usa: el del usuario o, si no hay, el de la tienda")
    source: Literal["user", "store", "none"]
    store_price: float | None
    store: str | None
    product_name: str | None
    url: str | None
    fetched_at: datetime | None = Field(description="Fecha del último precio válido de la tienda")
    status: str | None = Field(description="ok | error: resultado del último intento con la tienda")


class PriceIn(BaseModel):
    price: float = Field(ge=0, le=1_000_000, description="Precio unitario en soles (S/)")
