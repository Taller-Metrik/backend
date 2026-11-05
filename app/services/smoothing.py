"""Suavizado del trazo del recorrido para obtener un plano rectangular.

Pasos (docs/03-algoritmos.md, sección 3):
1. Ramer-Douglas-Peucker para simplificar el trazo.
2. Orientación dominante del ambiente (media circular de 4·θ ponderada por longitud).
3. Ortogonalización: cada lado se ajusta a 0°/90°/180°/270° respecto a esa orientación.
4. Fusión de lados consecutivos colineales.
5. Cierre del polígono repartiendo el error con la regla del tránsito
   (variante de Bowditch que reparte por eje y conserva la ortogonalidad).
"""

import math
from dataclasses import dataclass

from app.services.geometry import GeometryError, Point, euclidean

Vector = tuple[float, float]


def snap_turn_angle(angle_deg: float, tolerance_deg: float = 15.0) -> float:
    """Ajusta un giro medido por el giroscopio al múltiplo de 90° más cercano si está dentro de la tolerancia."""
    nearest = round(angle_deg / 90.0) * 90.0
    return nearest if abs(angle_deg - nearest) <= tolerance_deg else angle_deg


def _perpendicular_distance(p: Point, a: Point, b: Point) -> float:
    length = euclidean(a, b)
    if length == 0:
        return euclidean(p, a)
    return abs((b[0] - a[0]) * (a[1] - p[1]) - (a[0] - p[0]) * (b[1] - a[1])) / length


def rdp(points: list[Point], epsilon: float) -> list[Point]:
    """Ramer-Douglas-Peucker iterativo (sin recursión, apto para trazos largos)."""
    if len(points) < 3:
        return list(points)
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        start, end = stack.pop()
        max_dist, index = 0.0, -1
        for i in range(start + 1, end):
            d = _perpendicular_distance(points[i], points[start], points[end])
            if d > max_dist:
                max_dist, index = d, i
        if index != -1 and max_dist > epsilon:
            keep[index] = True
            stack.append((start, index))
            stack.append((index, end))
    return [p for p, k in zip(points, keep, strict=True) if k]


def dominant_orientation(edges: list[Vector]) -> float:
    """Ángulo dominante (radianes, en [-45°, 45°)) de un conjunto de lados, módulo 90°."""
    sx = sy = 0.0
    for dx, dy in edges:
        length = math.hypot(dx, dy)
        theta = math.atan2(dy, dx)
        sx += length * math.cos(4 * theta)
        sy += length * math.sin(4 * theta)
    if abs(sx) < 1e-12 and abs(sy) < 1e-12:
        return 0.0
    return math.atan2(sy, sx) / 4.0


def _rotate(v: Vector, angle: float) -> Vector:
    c, s = math.cos(angle), math.sin(angle)
    return (v[0] * c - v[1] * s, v[0] * s + v[1] * c)


def moving_average(points: list[Point], window: int) -> list[Point]:
    """Media móvil centrada para atenuar el temblor del trazo. Conserva los extremos."""
    if window <= 1 or len(points) <= window:
        return list(points)
    half = window // 2
    out: list[Point] = [points[0]]
    for i in range(1, len(points) - 1):
        lo, hi = max(0, i - half), min(len(points), i + half + 1)
        chunk = points[lo:hi]
        out.append((sum(p[0] for p in chunk) / len(chunk), sum(p[1] for p in chunk) / len(chunk)))
    out.append(points[-1])
    return out


def _merge_and_prune(edges: list[tuple[Vector, int | None]], min_wall_m: float) -> list[tuple[Vector, int | None]]:
    """Fusiona lados consecutivos con la misma dirección y elimina lados menores a una pared mínima.

    Se repite hasta que no haya cambios. El desplazamiento de los lados eliminados se
    compensa después con la corrección de cierre.
    """
    current = list(edges)
    while True:
        merged: list[tuple[Vector, int | None]] = []
        for vec, d in current:
            if merged and d is not None and merged[-1][1] == d:
                pv, _ = merged[-1]
                merged[-1] = ((pv[0] + vec[0], pv[1] + vec[1]), d)
            else:
                merged.append((vec, d))
        if len(merged) > 1 and merged[0][1] is not None and merged[0][1] == merged[-1][1]:
            last, d = merged.pop()
            first, _ = merged[0]
            merged[0] = ((last[0] + first[0], last[1] + first[1]), d)

        # Los lados no ortogonales (residuos de esquinas) se eliminan con un umbral mayor
        def weight(i: int) -> float:
            vec, d = merged[i]
            return math.hypot(*vec) / (1.0 if d is not None else 2.0)

        shortest = min(range(len(merged)), key=weight)
        if len(merged) > 4 and weight(shortest) < min_wall_m:
            merged.pop(shortest)
        if merged == current:
            return merged
        current = merged


def _point_segment_distance(p: Point, a: Point, b: Point) -> float:
    abx, aby = b[0] - a[0], b[1] - a[1]
    denom = abx * abx + aby * aby
    t = 0.0 if denom == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * abx + (p[1] - a[1]) * aby) / denom))
    return math.hypot(p[0] - (a[0] + t * abx), p[1] - (a[1] + t * aby))


def _least_squares_walls(vertices: list[Point], directions: list[int | None], raw: list[Point]) -> list[Point]:
    """Ajusta cada pared ortogonal a la media de los puntos crudos más cercanos a ella.

    Una pared horizontal (dirección 0 o 2) queda en y = media(y); una vertical (1 o 3)
    en x = media(x). Cada esquina es la intersección de dos paredes consecutivas, por lo
    que el resultado sigue siendo ortogonal y cerrado.
    """
    n = len(vertices)
    offsets: list[float] = []
    for i in range(n):
        horizontal = directions[i] in (0, 2)
        offsets.append(vertices[i][1] if horizontal else vertices[i][0])

    buckets: list[list[float]] = [[] for _ in range(n)]
    for p in raw:
        nearest = min(range(n), key=lambda i: _point_segment_distance(p, vertices[i], vertices[(i + 1) % n]))
        buckets[nearest].append(p[1] if directions[nearest] in (0, 2) else p[0])
    for i, values in enumerate(buckets):
        if values:
            offsets[i] = sum(values) / len(values)

    refined: list[Point] = []
    for i in range(n):
        prev = (i - 1) % n
        if directions[i] in (0, 2):  # pared i horizontal, pared anterior vertical
            refined.append((offsets[prev], offsets[i]))
        else:  # pared i vertical, pared anterior horizontal
            refined.append((offsets[i], offsets[prev]))
    return refined


@dataclass(frozen=True)
class SmoothingResult:
    vertices: list[Point]
    input_points: int
    simplified_points: int
    closed: bool
    closure_error_m: float
    dominant_angle_deg: float
    snapped_edges: int
    total_edges: int


def smooth_track(
    points: list[Point],
    *,
    corners: list[Point] | None = None,
    epsilon: float = 0.10,
    snap_tolerance_deg: float = 15.0,
    closure_tolerance_m: float = 1.0,
    min_edge_m: float = 0.05,
    min_wall_m: float = 0.30,
    smoothing_window: int = 5,
) -> SmoothingResult:
    """Convierte el trazo crudo (o las esquinas marcadas) en un polígono ortogonal cerrado.

    Si se envían `corners` (esquinas marcadas por el usuario) se usan como vértices;
    si no, se obtienen con RDP a partir de `points`.
    El recorrido se considera cerrado si termina a menos de `closure_tolerance_m` del inicio;
    si no, el hueco se agrega como un lado más (cierre automático, EX-01) y `closed=False`.
    """
    source = corners if corners else points
    walk: list[Point] = []
    for p in source:
        q = (float(p[0]), float(p[1]))
        if not walk or euclidean(walk[-1], q) > 1e-9:
            walk.append(q)
    if len(walk) < 3:
        raise GeometryError("El recorrido necesita al menos 3 puntos distintos")

    simplified = walk if corners else rdp(moving_average(walk, smoothing_window), epsilon)
    closed = euclidean(simplified[0], simplified[-1]) <= closure_tolerance_m
    if not closed:
        simplified = [*simplified, simplified[0]]  # cierre automático con el hueco como lado

    edges: list[Vector] = [
        (simplified[i + 1][0] - simplified[i][0], simplified[i + 1][1] - simplified[i][1])
        for i in range(len(simplified) - 1)
    ]
    edges = [e for e in edges if math.hypot(*e) >= min_edge_m]
    if len(edges) < 3:
        raise GeometryError("El recorrido es demasiado corto para formar un polígono")

    closure_error = math.hypot(sum(e[0] for e in edges), sum(e[1] for e in edges))

    # Orientación dominante y ortogonalización en el marco rotado
    alpha = dominant_orientation(edges)
    tol = math.radians(snap_tolerance_deg)
    local: list[tuple[Vector, int | None]] = []
    snapped = 0
    for e in edges:
        dx, dy = _rotate(e, -alpha)
        length = math.hypot(dx, dy)
        phi = math.atan2(dy, dx)
        k = round(phi / (math.pi / 2))
        if abs(phi - k * math.pi / 2) <= tol:
            snapped += 1
            direction = k % 4
            local.append(((length * math.cos(k * math.pi / 2), length * math.sin(k * math.pi / 2)), direction))
        else:
            local.append(((dx, dy), None))

    merged = _merge_and_prune(local, min_wall_m)
    if len(merged) < 3:
        raise GeometryError("El recorrido suavizado tiene menos de 3 lados")

    # Regla del tránsito: repartir el error de cierre por eje
    vecs = [v for v, _ in merged]
    ex, ey = sum(v[0] for v in vecs), sum(v[1] for v in vecs)
    sx, sy = sum(abs(v[0]) for v in vecs), sum(abs(v[1]) for v in vecs)
    corrected = [
        (
            v[0] - (ex * abs(v[0]) / sx if sx > 0 else 0.0),
            v[1] - (ey * abs(v[1]) / sy if sy > 0 else 0.0),
        )
        for v in vecs
    ]

    # Reconstruir vértices desde el primer punto del recorrido
    current = (0.0, 0.0)
    local_vertices = [current]
    for v in corrected[:-1]:
        current = (current[0] + v[0], current[1] + v[1])
        local_vertices.append(current)

    x0, y0 = simplified[0]
    directions = [d for _, d in merged]
    alternating = all(d is not None for d in directions) and all(
        directions[i] % 2 != directions[(i + 1) % len(directions)] % 2 for i in range(len(directions))
    )
    if not corners and alternating:
        raw_local = [_rotate((p[0] - x0, p[1] - y0), -alpha) for p in walk]
        local_vertices = _least_squares_walls(local_vertices, directions, raw_local)

    vertices = [
        (round(x0 + r[0], 6), round(y0 + r[1], 6)) for r in (_rotate(p, alpha) for p in local_vertices)
    ]
    if len(vertices) < 3:
        raise GeometryError("El recorrido suavizado tiene menos de 3 vértices")

    return SmoothingResult(
        vertices=vertices,
        input_points=len(source),
        simplified_points=len(simplified) - (0 if closed else 1),
        closed=closed,
        closure_error_m=closure_error,
        dominant_angle_deg=math.degrees(alpha),
        snapped_edges=snapped,
        total_edges=len(edges),
    )
