"""Datos de campo crudos: lecturas de sensores, pruebas GPS y calibraciones."""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.survey import JsonType


class SensorReading(Base):
    """Lectura cruda de un recorrido: giroscopio/acelerómetro (motion), GPS o esquina marcada."""

    __tablename__ = "sensor_readings"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    survey_id: Mapped[int] = mapped_column(ForeignKey("surveys.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    t_ms: Mapped[int] = mapped_column(BigInteger)
    kind: Mapped[str] = mapped_column(String(16))  # motion | gps | corner
    gyro_z_dps: Mapped[float | None] = mapped_column(Float, default=None)
    accel_x: Mapped[float | None] = mapped_column(Float, default=None)
    accel_y: Mapped[float | None] = mapped_column(Float, default=None)
    accel_z: Mapped[float | None] = mapped_column(Float, default=None)
    lat: Mapped[float | None] = mapped_column(Float, default=None)
    lon: Mapped[float | None] = mapped_column(Float, default=None)
    accuracy_m: Mapped[float | None] = mapped_column(Float, default=None)


class GpsTrial(Base):
    """Prueba de precisión GPS: lecturas en dos puntos separados por una distancia real conocida."""

    __tablename__ = "gps_trials"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    device_id: Mapped[str | None] = mapped_column(String(80), default=None)
    place_name: Mapped[str | None] = mapped_column(String(120), default=None)
    environment: Mapped[str | None] = mapped_column(String(40), default=None)
    real_distance_m: Mapped[float] = mapped_column(Float)
    start_fixes: Mapped[list[Any]] = mapped_column(JsonType)
    end_fixes: Mapped[list[Any]] = mapped_column(JsonType)
    measured_distance_m: Mapped[float | None] = mapped_column(Float, default=None)
    error_m: Mapped[float | None] = mapped_column(Float, default=None)
    source_ref: Mapped[str | None] = mapped_column(String(120), unique=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SensorCalibration(Base):
    """Calibración de sensores (sesgo del giroscopio, largo de paso, ajustes de precisión)."""

    __tablename__ = "sensor_calibrations"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    device_id: Mapped[str | None] = mapped_column(String(80), default=None)
    kind: Mapped[str] = mapped_column(String(40))
    origin: Mapped[str | None] = mapped_column(String(40), default=None)
    params: Mapped[dict[str, Any]] = mapped_column(JsonType)
    applied: Mapped[bool | None] = mapped_column(Boolean, default=None)
    source_ref: Mapped[str | None] = mapped_column(String(120), unique=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
