"""Cálculo geométrico de polígonos en el plano (metros).

Ver docs/03-algoritmos.md, sección 4.
"""

import math
from dataclasses import dataclass, field

Point = tuple[float, float]

_EPS = 1e-9


class GeometryError(ValueError):
    """Entrada geométrica inválida (p. ej. menos de 3 vértices)."""


# ---------------------------------------------------------------- distancias


def euclidean(a: Point, b: Point) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def manhattan(a: Point, b: Point) -> float:
    return abs(b[0] - a[0]) + abs(b[1] - a[1])


# ---------------------------------------------------------------- polígonos


def normalize_polygon(vertices: list[Point]) -> list[Point]:
    """Quita vértices consecutivos repetidos y el punto de cierre duplicado."""
    cleaned: list[Point] = []
    for v in vertices:
        p = (float(v[0]), float(v[1]))
        if not cleaned or euclidean(cleaned[-1], p) > _EPS:
            cleaned.append(p)
    if len(cleaned) > 1 and euclidean(cleaned[0], cleaned[-1]) <= _EPS:
        cleaned.pop()
    if len(cleaned) < 3:
        raise GeometryError("Se necesitan al menos 3 vértices distintos para formar un polígono")
    return cleaned


def signed_area(vertices: list[Point]) -> float:
    """Área con signo por la fórmula de Gauss (Shoelace). Positiva = antihorario."""
    total = 0.0
    n = len(vertices)
    for i in range(n):
        x1, y1 = vertices[i]
        x2, y2 = vertices[(i + 1) % n]
        total += x1 * y2 - x2 * y1
    return total / 2.0


def area(vertices: list[Point]) -> float:
    return abs(signed_area(normalize_polygon(vertices)))


def segment_lengths(vertices: list[Point]) -> list[float]:
    n = len(vertices)
    return [euclidean(vertices[i], vertices[(i + 1) % n]) for i in range(n)]


def perimeter(vertices: list[Point]) -> float:
    return sum(segment_lengths(normalize_polygon(vertices)))


def interior_angles(vertices: list[Point]) -> list[float]:
    """Ángulo interior (grados) en cada vértice. > 180° indica vértice cóncavo."""
    poly = normalize_polygon(vertices)
    ccw = signed_area(poly) > 0
    n = len(poly)
    angles: list[float] = []
    for i in range(n):
        vx, vy = poly[i]
        ax, ay = poly[i - 1][0] - vx, poly[i - 1][1] - vy  # hacia el anterior
        bx, by = poly[(i + 1) % n][0] - vx, poly[(i + 1) % n][1] - vy  # hacia el siguiente
        cross = bx * ay - by * ax if ccw else ax * by - ay * bx
        dot = ax * bx + ay * by
        angle = math.degrees(math.atan2(cross, dot)) % 360.0
        angles.append(angle)
    return angles


def _segments_intersect(p1: Point, p2: Point, p3: Point, p4: Point) -> bool:
    def orient(a: Point, b: Point, c: Point) -> float:
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    d1, d2 = orient(p3, p4, p1), orient(p3, p4, p2)
    d3, d4 = orient(p1, p2, p3), orient(p1, p2, p4)
    return ((d1 > _EPS and d2 < -_EPS) or (d1 < -_EPS and d2 > _EPS)) and (
        (d3 > _EPS and d4 < -_EPS) or (d3 < -_EPS and d4 > _EPS)
    )


def is_simple(vertices: list[Point]) -> bool:
    """True si ningún par de lados no adyacentes se cruza (polígono no autointersectado)."""
    poly = normalize_polygon(vertices)
    n = len(poly)
    for i in range(n):
        a1, a2 = poly[i], poly[(i + 1) % n]
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue  # lados adyacentes por el cierre
            if _segments_intersect(a1, a2, poly[j], poly[(j + 1) % n]):
                return False
    return True


@dataclass(frozen=True)
class PolygonAnalysis:
    vertices: list[Point]
    area_m2: float
    perimeter_m: float
    wall_lengths_m: list[float]
    interior_angles_deg: list[float]
    concave_vertices: list[int]
    is_convex: bool
    is_simple: bool
    orientation: str
    angle_sum_deg: float
    expected_angle_sum_deg: float = field(default=0.0)


def analyze(vertices: list[Point]) -> PolygonAnalysis:
    """Análisis completo: área, perímetro, muros, ángulos y convexidad."""
    poly = normalize_polygon(vertices)
    simple = is_simple(poly)
    angles = interior_angles(poly)
    concave = [i for i, a in enumerate(angles) if a > 180.0 + 1e-6]
    walls = segment_lengths(poly)
    return PolygonAnalysis(
        vertices=poly,
        area_m2=abs(signed_area(poly)),
        perimeter_m=sum(walls),
        wall_lengths_m=walls,
        interior_angles_deg=angles,
        concave_vertices=concave,
        is_convex=not concave,
        is_simple=simple,
        orientation="antihorario" if signed_area(poly) > 0 else "horario",
        angle_sum_deg=sum(angles),
        expected_angle_sum_deg=(len(poly) - 2) * 180.0,
    )
