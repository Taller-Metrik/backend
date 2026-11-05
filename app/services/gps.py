"""Modo exterior: GPS → coordenadas métricas, filtrado y margen de error.

Ver docs/03-algoritmos.md, sección 5.
"""

import math
import statistics
from dataclasses import dataclass

from app.services.geometry import GeometryError, Point
from app.services.smoothing import rdp

EARTH_RADIUS_M = 6_371_000.0


@dataclass(frozen=True)
class GpsReading:
    lat: float
    lon: float
    accuracy_m: float = 5.0
    timestamp_s: float | None = None


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


def filter_by_accuracy(readings: list[GpsReading], max_accuracy_m: float) -> tuple[list[GpsReading], int]:
    """Descarta lecturas cuya precisión reportada supera el umbral. Devuelve (válidas, descartadas)."""
    valid = [r for r in readings if r.accuracy_m <= max_accuracy_m]
    return valid, len(readings) - len(valid)


def kalman_smooth(
    points: list[Point],
    timestamps: list[float],
    accuracies: list[float],
    process_noise: float = 0.5,
) -> list[Point]:
    """Filtro de Kalman de velocidad constante + suavizador RTS, independiente por eje.

    `process_noise` es la desviación de la aceleración (m/s²); la varianza de medida
    se toma de la precisión reportada por el GPS. La pasada hacia atrás
    (Rauch-Tung-Striebel) elimina el retardo del filtro, que redondearía las esquinas.
    """
    n = len(points)
    if n < 2:
        return list(points)
    q = process_noise**2
    out: list[list[float]] = [[0.0, 0.0] for _ in points]
    for axis in (0, 1):
        # Estados y covarianzas filtradas (f) y predichas (p): x=[pos, vel], P=[[a, b], [b, c]]
        xf: list[tuple[float, float]] = []
        pf: list[tuple[float, float, float]] = []
        xp: list[tuple[float, float]] = [(0.0, 0.0)]
        pp: list[tuple[float, float, float]] = [(0.0, 0.0, 0.0)]
        x, v = points[0][axis], 0.0
        a, b, c = accuracies[0] ** 2, 0.0, 25.0
        xf.append((x, v))
        pf.append((a, b, c))
        for i in range(1, n):
            dt = max(1e-3, timestamps[i] - timestamps[i - 1])
            x, v = x + v * dt, v
            a, b, c = (
                a + 2 * dt * b + dt * dt * c + q * dt**4 / 4,
                b + dt * c + q * dt**3 / 2,
                c + q * dt * dt,
            )
            xp.append((x, v))
            pp.append((a, b, c))
            r = max(accuracies[i], 0.5) ** 2
            s = a + r
            k1, k2 = a / s, b / s
            innovation = points[i][axis] - x
            x, v = x + k1 * innovation, v + k2 * innovation
            a, b, c = (1 - k1) * a, (1 - k1) * b, c - k2 * b
            xf.append((x, v))
            pf.append((a, b, c))

        # Suavizador RTS (pasada hacia atrás)
        xs, vs = xf[-1]
        sa, sb, sc = pf[-1]
        out[-1][axis] = xs
        for i in range(n - 2, -1, -1):
            dt = max(1e-3, timestamps[i + 1] - timestamps[i])
            fa, fb, fc = pf[i]
            pa, pb, pc = pp[i + 1]
            # C = P_f · Fᵀ · P_p⁻¹, con F = [[1, dt], [0, 1]]
            m11, m12, m21, m22 = fa + fb * dt, fb, fb + fc * dt, fc
            det = pa * pc - pb * pb
            if abs(det) < 1e-12:
                xs, vs = xf[i]
                out[i][axis] = xs
                continue
            ia, ib, ic = pc / det, -pb / det, pa / det
            c11, c12 = m11 * ia + m12 * ib, m11 * ib + m12 * ic
            c21, c22 = m21 * ia + m22 * ib, m21 * ib + m22 * ic
            dx, dv = xs - xp[i + 1][0], vs - xp[i + 1][1]
            xs = xf[i][0] + c11 * dx + c12 * dv
            vs = xf[i][1] + c21 * dx + c22 * dv
            out[i][axis] = xs
    return [(p[0], p[1]) for p in out]


@dataclass(frozen=True)
class GpsErrorMetrics:
    n: int
    reference: tuple[float, float]
    reference_is_mean: bool
    mean_error_m: float
    cep50_m: float
    r95_m: float
    drms_m: float
    two_drms_m: float
    max_error_m: float
    needs_calibration: bool


def _percentile(sorted_values: list[float], q: float) -> float:
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = (len(sorted_values) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def error_metrics(
    readings: list[GpsReading],
    reference: tuple[float, float] | None = None,
    calibration_threshold_m: float = 8.0,
) -> GpsErrorMetrics:
    """Margen de error de lecturas estáticas respecto a un punto conocido (o a su media)."""
    if len(readings) < 2:
        raise GeometryError("Se necesitan al menos 2 lecturas para estimar el error")
    reference_is_mean = reference is None
    if reference is None:
        reference = (statistics.fmean(r.lat for r in readings), statistics.fmean(r.lon for r in readings))
    xy = to_enu(readings, origin=reference)
    distances = sorted(math.hypot(x, y) for x, y in xy)
    sx = statistics.pstdev(p[0] for p in xy) if reference_is_mean else math.sqrt(statistics.fmean(p[0] ** 2 for p in xy))
    sy = statistics.pstdev(p[1] for p in xy) if reference_is_mean else math.sqrt(statistics.fmean(p[1] ** 2 for p in xy))
    drms = math.hypot(sx, sy)
    cep = statistics.median(distances)
    return GpsErrorMetrics(
        n=len(readings),
        reference=reference,
        reference_is_mean=reference_is_mean,
        mean_error_m=statistics.fmean(distances),
        cep50_m=cep,
        r95_m=_percentile(distances, 0.95),
        drms_m=drms,
        two_drms_m=2 * drms,
        max_error_m=distances[-1],
        needs_calibration=cep > calibration_threshold_m,
    )


def _fit_line(points: list[Point]) -> tuple[Point, Point] | None:
    """Recta por mínimos cuadrados totales (PCA): (centroide, dirección unitaria)."""
    if len(points) < 2:
        return None
    cx = statistics.fmean(p[0] for p in points)
    cy = statistics.fmean(p[1] for p in points)
    sxx = sum((p[0] - cx) ** 2 for p in points)
    syy = sum((p[1] - cy) ** 2 for p in points)
    sxy = sum((p[0] - cx) * (p[1] - cy) for p in points)
    theta = 0.5 * math.atan2(2 * sxy, sxx - syy)
    return (cx, cy), (math.cos(theta), math.sin(theta))


def _intersect(l1: tuple[Point, Point], l2: tuple[Point, Point]) -> Point | None:
    (p, d), (q, e) = l1, l2
    denom = d[0] * e[1] - d[1] * e[0]
    if abs(denom) < 0.05:  # casi paralelas (< ~3°)
        return None
    t = ((q[0] - p[0]) * e[1] - (q[1] - p[1]) * e[0]) / denom
    return (p[0] + t * d[0], p[1] + t * d[1])


def refine_vertices_by_lines(vertices: list[Point], track: list[Point], exclude_radius_m: float) -> list[Point]:
    """Reubica cada vértice en la intersección de las rectas ajustadas a sus dos lados.

    Cada punto del trazo se asigna al lado más cercano; se excluyen los puntos a menos de
    `exclude_radius_m` de un vértice para que el redondeo de la esquina no sesgue el ajuste.
    """
    n = len(vertices)

    def seg_dist(p: Point, a: Point, b: Point) -> float:
        abx, aby = b[0] - a[0], b[1] - a[1]
        den = abx * abx + aby * aby
        t = 0.0 if den == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * abx + (p[1] - a[1]) * aby) / den))
        return math.hypot(p[0] - a[0] - t * abx, p[1] - a[1] - t * aby)

    buckets: list[list[Point]] = [[] for _ in range(n)]
    for p in track:
        if min(math.dist(p, v) for v in vertices) < exclude_radius_m:
            continue
        i = min(range(n), key=lambda k: seg_dist(p, vertices[k], vertices[(k + 1) % n]))
        buckets[i].append(p)

    lines = [_fit_line(b) for b in buckets]
    refined: list[Point] = []
    for i in range(n):
        prev_line, line = lines[(i - 1) % n], lines[i]
        point = _intersect(prev_line, line) if prev_line and line else None
        if point is None or math.dist(point, vertices[i]) > 4 * exclude_radius_m:
            point = vertices[i]
        refined.append(point)
    return refined


@dataclass(frozen=True)
class GpsPolygon:
    vertices: list[Point]
    origin: tuple[float, float]
    used_readings: int
    discarded_readings: int


def gps_polygon(
    readings: list[GpsReading],
    *,
    max_accuracy_m: float = 10.0,
    simplify_epsilon_m: float | None = None,
    use_kalman: bool = True,
) -> GpsPolygon:
    """Convierte el recorrido GPS de un área en un polígono métrico (para área y perímetro).

    Si no se indica `simplify_epsilon_m`, se usa 2 × la precisión mediana de las lecturas:
    el ruido residual genera un zigzag que infla el perímetro (el área es mucho más robusta).
    """
    valid, discarded = filter_by_accuracy(readings, max_accuracy_m)
    if len(valid) < 3:
        raise GeometryError(
            f"Solo {len(valid)} lecturas con precisión ≤ {max_accuracy_m} m; se necesitan al menos 3 (EX-04)"
        )
    if simplify_epsilon_m is None:
        simplify_epsilon_m = max(1.0, 2 * statistics.median(r.accuracy_m for r in valid))
    xy = to_enu(valid)
    if use_kalman and all(r.timestamp_s is not None for r in valid):
        xy = kalman_smooth(xy, [r.timestamp_s for r in valid], [r.accuracy_m for r in valid])  # type: ignore[misc]
    vertices = rdp(xy, simplify_epsilon_m) if len(xy) > 3 else xy
    if len(vertices) > 3 and math.hypot(vertices[0][0] - vertices[-1][0], vertices[0][1] - vertices[-1][1]) < max(
        simplify_epsilon_m, 1.0
    ):
        vertices = vertices[:-1]
    if len(vertices) >= 3:
        vertices = refine_vertices_by_lines(vertices, xy, exclude_radius_m=simplify_epsilon_m)
    return GpsPolygon(
        vertices=vertices,
        origin=(valid[0].lat, valid[0].lon),
        used_readings=len(valid),
        discarded_readings=discarded,
    )
