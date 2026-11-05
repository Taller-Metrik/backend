"""Utilidades de prueba: simulación de recorridos con ruido."""

import math
import random

Point = tuple[float, float]

RECTANGULO_5x4: list[Point] = [(0, 0), (5, 0), (5, 4), (0, 4)]
AMBIENTE_L: list[Point] = [(0, 0), (6, 0), (6, 3), (3, 3), (3, 5), (0, 5)]  # área 24 m², cóncavo
AMBIENTE_U: list[Point] = [(0, 0), (6, 0), (6, 5), (4, 5), (4, 2), (2, 2), (2, 5), (0, 5)]  # área 24 m²


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
