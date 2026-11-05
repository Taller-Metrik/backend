"""Medida real (wincha) de un muro, para calcular el margen de error de la app."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.survey import JsonType


class ReferenceMeasurement(Base):
    __tablename__ = "reference_measurements"
    __table_args__ = (UniqueConstraint("survey_id", "wall_index", name="uq_reference_survey_wall"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    survey_id: Mapped[int] = mapped_column(ForeignKey("surveys.id", ondelete="CASCADE"), index=True)
    wall_index: Mapped[int] = mapped_column(Integer)
    readings_m: Mapped[list[Any]] = mapped_column(JsonType)  # lecturas de wincha
    real_length_m: Mapped[float] = mapped_column(Float)  # promedio de las lecturas
    notes: Mapped[str | None] = mapped_column(String(255), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
