"""Recorrido (survey): una medición de un ambiente o área con el celular."""

import enum
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.project import Project

JsonType = JSON().with_variant(JSONB(), "postgresql")


class SurveyMode(enum.StrEnum):
    INTERIOR = "interior"  # odómetro ARCore / pasos
    EXTERIOR = "exterior"  # GPS
    IMPORTED = "imported"  # medido sobre un plano importado


class Survey(Base):
    __tablename__ = "surveys"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    mode: Mapped[SurveyMode] = mapped_column(Enum(SurveyMode, name="survey_mode"))
    device_model: Mapped[str | None] = mapped_column(String(120), default=None)

    # Datos crudos
    raw_points: Mapped[list[Any]] = mapped_column(JsonType, default=list)
    corners: Mapped[list[Any] | None] = mapped_column(JsonType, default=None)
    gps_points: Mapped[list[Any] | None] = mapped_column(JsonType, default=None)

    # Resultado del procesamiento
    vertices: Mapped[list[Any]] = mapped_column(JsonType, default=list)
    wall_lengths_m: Mapped[list[Any]] = mapped_column(JsonType, default=list)
    interior_angles_deg: Mapped[list[Any]] = mapped_column(JsonType, default=list)
    area_m2: Mapped[float] = mapped_column(Float)
    perimeter_m: Mapped[float] = mapped_column(Float)
    closure_error_m: Mapped[float] = mapped_column(Float, default=0.0)
    closed: Mapped[bool] = mapped_column(Boolean, default=True)
    is_simple: Mapped[bool] = mapped_column(Boolean, default=True)
    concave_count: Mapped[int] = mapped_column(Integer, default=0)
    scale_denominator: Mapped[int] = mapped_column(Integer)

    # Validación (medida real del área, opcional; las de cada muro van en ReferenceMeasurement)
    real_area_m2: Mapped[float | None] = mapped_column(Float, default=None)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped["Project"] = relationship(back_populates="surveys")
