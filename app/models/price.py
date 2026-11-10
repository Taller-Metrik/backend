"""Catálogo de precios de materiales (RF-23): precio de tienda por scraping y precio propio del usuario."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MaterialPrice(Base):
    """Último precio leído de la tienda para un material del catálogo (una fila por material)."""

    __tablename__ = "material_prices"

    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    store: Mapped[str] = mapped_column(String(40))
    product_name: Mapped[str | None] = mapped_column(String(200), default=None)
    url: Mapped[str | None] = mapped_column(String(300), default=None)
    price: Mapped[float | None] = mapped_column(Numeric(10, 2, asdecimal=False), default=None)
    available: Mapped[bool] = mapped_column(Boolean, default=False)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)  # último precio válido
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())  # último intento
    status: Mapped[str] = mapped_column(String(10), default="ok")  # ok | error
    error: Mapped[str | None] = mapped_column(String(200), default=None)


class UserPrice(Base):
    """Precio que el usuario escribe para un material; tiene prioridad sobre el de la tienda."""

    __tablename__ = "user_prices"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_user_price_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(40))
    price: Mapped[float] = mapped_column(Numeric(10, 2, asdecimal=False))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
