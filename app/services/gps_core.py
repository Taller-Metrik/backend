"""Núcleo GPS: la lectura y la proyección a metros, sin dependencias de otros servicios GPS.

`gps` (filtros, Kalman, polígono) y `gps_precision` (esquinas fijadas) dependen de este módulo;
así ninguno de los dos depende del otro de forma circular.
"""

import math
from dataclasses import dataclass

from app.services.geometry import Point

EARTH_RADIUS_M = 6_371_000.0


@dataclass(frozen=True)
class GpsReading:
    lat: float
    lon: float
    accuracy_m: float = 5.0
    timestamp_s: float | None = None
    satellites: int | None = None  # satélites usados en la solución (usedInFix)
    cn0_dbhz: float | None = None  # C/N0 medio de los 4 satélites usados más fuertes
    vertex_id: int | None = None  # esquina sobre la que el usuario está quieto (stop-and-go)


def haversine(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Distancia geodésica (m) entre dos coordenadas (lat, lon) en grados."""
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def to_enu(readings: list[GpsReading], origin: tuple[float, float] | None = None) -> list[Point]:
    """Proyección equirrectangular local: (lat, lon) → (x este, y norte) en metros."""
    if not readings:
        return []
    lat0, lon0 = origin if origin else (readings[0].lat, readings[0].lon)
    cos_lat0 = math.cos(math.radians(lat0))
    return [
        (
            EARTH_RADIUS_M * math.radians(r.lon - lon0) * cos_lat0,
            EARTH_RADIUS_M * math.radians(r.lat - lat0),
        )
        for r in readings
    ]
