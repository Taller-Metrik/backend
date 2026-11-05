"""Utilidades de prueba: simulación de recorridos con ruido."""

import math
import random

Point = tuple[float, float]

RECTANGULO_5x4: list[Point] = [(0, 0), (5, 0), (5, 4), (0, 4)]
AMBIENTE_L: list[Point] = [(0, 0), (6, 0), (6, 3), (3, 3), (3, 5), (0, 5)]  # área 24 m², cóncavo
AMBIENTE_U: list[Point] = [(0, 0), (6, 0), (6, 5), (4, 5), (4, 2), (2, 2), (2, 5), (0, 5)]  # área 24 m²


ORIGEN_TRUJILLO = (-8.1300, -79.0400)  # punto de referencia (lat, lon)
TERRENO_100x60: list[Point] = [(0, 0), (100, 0), (100, 60), (0, 60)]  # 6000 m²


def simulate_gps_walk(
    polygon: list[Point],
    *,
    origin: tuple[float, float] = ORIGEN_TRUJILLO,
    step_m: float = 2.0,
    noise_m: float = 3.0,
    accuracy_m: float = 4.0,
    outlier_every: int = 0,
    seed: int = 1,
) -> list[dict]:
    """Simula lecturas GPS (lat, lon) recorriendo un polígono en metros (x=este, y=norte)."""
    rng = random.Random(seed)
    lat0, lon0 = origin
    r_earth = 6_371_000.0
    readings: list[dict] = []
    n = len(polygon)
    t = 0.0
    for i in range(n):
        (x1, y1), (x2, y2) = polygon[i], polygon[(i + 1) % n]
        steps = max(1, int(math.hypot(x2 - x1, y2 - y1) / step_m))
        for k in range(steps):
            f = k / steps
            x = x1 + (x2 - x1) * f + rng.gauss(0, noise_m)
            y = y1 + (y2 - y1) * f + rng.gauss(0, noise_m)
            acc = accuracy_m
            if outlier_every and len(readings) % outlier_every == outlier_every - 1:
                x += rng.choice((-1, 1)) * 35
                acc = 30.0
            lat = lat0 + math.degrees(y / r_earth)
            lon = lon0 + math.degrees(x / (r_earth * math.cos(math.radians(lat0))))
            readings.append({"lat": lat, "lon": lon, "accuracy_m": acc, "timestamp_s": t})
            t += 1.5
    return readings


def simulate_static_gps(n: int, *, sigma_m: float, origin=ORIGEN_TRUJILLO, seed: int = 1) -> list[dict]:
    """Lecturas GPS con el celular quieto en `origin` y ruido gaussiano de `sigma_m` por eje."""
    rng = random.Random(seed)
    lat0, lon0 = origin
    r_earth = 6_371_000.0
    out = []
    for i in range(n):
        dx, dy = rng.gauss(0, sigma_m), rng.gauss(0, sigma_m)
        out.append(
            {
                "lat": lat0 + math.degrees(dy / r_earth),
                "lon": lon0 + math.degrees(dx / (r_earth * math.cos(math.radians(lat0)))),
                "accuracy_m": sigma_m,
                "timestamp_s": float(i),
            }
        )
    return out


def simulate_walk(
    polygon: list[Point],
    *,
    step_m: float = 0.05,
    noise_m: float = 0.03,
    rotation_deg: float = 20.0,
    seed: int = 1,
) -> list[Point]:
    """Simula el trazo de un recorrido por el perímetro con ruido gaussiano y rotación."""
    rng = random.Random(seed)
    a = math.radians(rotation_deg)
    pts: list[Point] = []
    n = len(polygon)
    for i in range(n):
        (x1, y1), (x2, y2) = polygon[i], polygon[(i + 1) % n]
        steps = max(1, int(math.hypot(x2 - x1, y2 - y1) / step_m))
        for k in range(steps):
            t = k / steps
            x = x1 + (x2 - x1) * t + rng.gauss(0, noise_m)
            y = y1 + (y2 - y1) * t + rng.gauss(0, noise_m)
            pts.append((x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)))
    pts.append(pts[0])
    return pts
