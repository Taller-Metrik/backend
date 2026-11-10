"""Precisión GPS: esquinas fijadas (stop-and-go), filtro por señal y σ de cada vértice (RF-18 a RF-20).

Con un celular de una sola frecuencia el error GPS está correlacionado durante decenas de segundos:
promediar 30 lecturas seguidas no lo divide entre √30. Por eso:

- la σ de una esquina usa un número efectivo de lecturas independientes (una cada
  `CORRELATION_TIME_S` segundos), nunca es menor que la precisión que reporta el propio GPS, y suma
  una parte que no se reduce al promediar (multitrayecto e ionosfera cambian en escalas de minutos):
      σ_v² = máx(dispersión, σ reportada)² / n_ef + σ_b²
- si el usuario vuelve a fijar la primera esquina al final, la distancia d entre ambas fijaciones es una
  medida real del error. Con σ por eje en cada fijación, d sigue una distribución de Rayleigh de
  parámetro σ·√2, cuyo valor esperado es σ·√π; por eso se usa d / √π como piso de σ. Si d supera el
  percentil 95 de esa distribución, la σ declarada no es creíble (`closure_consistent = False`).
"""

import math
import statistics
from dataclasses import dataclass

from app.services.geometry import GeometryError, Point
from app.services.gps_core import GpsReading, to_enu

# Android informa `accuracy` como el radio que contiene el 68 % de las posiciones. Para un error
# gaussiano 2D con σ por eje: P(r ≤ R) = 1 − exp(−R²/2σ²) = 0,68  ⇒  R = σ·√(−2·ln 0,32) ≈ 1,5096·σ
ANDROID_ACCURACY_TO_SIGMA = math.sqrt(-2 * math.log(0.32))
MIN_SIGMA_M = 0.3  # piso de σ de una lectura individual
NON_AVERAGING_SIGMA_M = 0.5  # σ_b: error que no se reduce al promediar (también es el piso de un vértice)
RAYLEIGH_P95 = math.sqrt(-2 * math.log(0.05))  # percentil 95 de Rayleigh / su parámetro = 2,448

MIN_SATELLITES = 6  # satélites usados en la solución
MIN_CN0_DBHZ = 30.0  # relación portadora/ruido media; por debajo hay obstrucción o multitrayecto

OUTLIER_SIGMAS = 3.0  # se descartan lecturas a más de 3σ del centro (conserva el 98,9 % de las normales)
RAYLEIGH_MEDIAN = math.sqrt(2 * math.log(2))  # mediana de la distancia radial = 1,1774·σ
CORRELATION_TIME_S = 30.0  # tiempo tras el cual dos lecturas GPS se consideran independientes
MIN_READINGS_PER_VERTEX = 3


def sigma_from_accuracy(accuracy_m: float) -> float:
    """σ por eje (m) a partir de la precisión de Android (radio del 68 %)."""
    return max(MIN_SIGMA_M, accuracy_m / ANDROID_ACCURACY_TO_SIGMA)


def filter_by_signal(
    readings: list[GpsReading],
    min_satellites: int = MIN_SATELLITES,
    min_cn0_dbhz: float = MIN_CN0_DBHZ,
) -> tuple[list[GpsReading], int]:
    """Descarta lecturas con pocos satélites o señal débil. Las lecturas sin esos datos se conservan."""
    kept = [
        r
        for r in readings
        if (r.satellites is None or r.satellites >= min_satellites)
        and (r.cn0_dbhz is None or r.cn0_dbhz >= min_cn0_dbhz)
    ]
    return kept, len(readings) - len(kept)


@dataclass(frozen=True)
class VertexFix:
    point: Point
    sigma_m: float  # σ por eje del vértice
    used: int
    rejected: int


def _weighted_mean(points: list[Point], weights: list[float]) -> Point:
    total = sum(weights)
    return (
        sum(p[0] * w for p, w in zip(points, weights, strict=True)) / total,
        sum(p[1] * w for p, w in zip(points, weights, strict=True)) / total,
    )


def fix_vertex(points: list[Point], sigmas_m: list[float], duration_s: float) -> VertexFix:
    """Fija una esquina con las lecturas tomadas quieto sobre ella.

    1. Centro robusto (mediana por eje) y σ robusta (mediana de la distancia radial / 1,1774).
    2. Descarta las lecturas a más de `OUTLIER_SIGMAS`·σ del centro.
    3. Promedio ponderado por 1/σᵢ² de las lecturas restantes.
    4. σ del vértice² = máx(dispersión, σ reportada media)² / n_ef + σ_b², con n_ef = duración / 30 s.
    """
    if not points:
        raise GeometryError("No hay lecturas para fijar la esquina")
    center = (statistics.median(p[0] for p in points), statistics.median(p[1] for p in points))
    radial = [math.dist(p, center) for p in points]
    robust_sigma = max(MIN_SIGMA_M, statistics.median(radial) / RAYLEIGH_MEDIAN)
    keep = [i for i, r in enumerate(radial) if r <= OUTLIER_SIGMAS * robust_sigma]
    if len(keep) < MIN_READINGS_PER_VERTEX:
        keep = list(range(len(points)))
    kept_points = [points[i] for i in keep]
    kept_sigmas = [max(MIN_SIGMA_M, sigmas_m[i]) for i in keep]
    weights = [1 / s**2 for s in kept_sigmas]
    point = _weighted_mean(kept_points, weights)
    spread = math.sqrt(sum(w * math.dist(p, point) ** 2 for p, w in zip(kept_points, weights, strict=True)) / (2 * sum(weights)))
    reported = statistics.fmean(kept_sigmas)
    n_eff = min(len(keep), max(1.0, duration_s / CORRELATION_TIME_S))
    sigma = math.sqrt(max(spread, reported) ** 2 / n_eff + NON_AVERAGING_SIGMA_M**2)
    return VertexFix(point=point, sigma_m=sigma, used=len(keep), rejected=len(points) - len(keep))


@dataclass(frozen=True)
class StopAndGo:
    vertices: list[Point]
    sigmas_m: list[float]
    closure_m: float | None  # distancia entre la primera fijación y la de cierre (RF-19)
    closure_consistent: bool | None  # False si el cierre supera el percentil 95 esperado por la σ
    closure_dominated: bool  # True si el cierre elevó la σ de algún vértice (σ estimada con 1 muestra)
    rejected: int


def _visits(readings: list[GpsReading]) -> list[tuple[int, list[GpsReading]]]:
    """Agrupa lecturas consecutivas con el mismo `vertex_id` (cada grupo es una visita a una esquina)."""
    visits: list[tuple[int, list[GpsReading]]] = []
    previous: int | None = None
    for r in readings:
        if r.vertex_id is None:
            previous = None
            continue
        if r.vertex_id == previous:
            visits[-1][1].append(r)
        else:
            visits.append((r.vertex_id, [r]))
        previous = r.vertex_id
    return visits


def _duration_s(visit: list[GpsReading]) -> float:
    """Tiempo quieto en una visita (no cuenta lo caminado entre visitas a la misma esquina)."""
    times = [r.timestamp_s for r in visit if r.timestamp_s is not None]
    if len(times) == len(visit) and len(times) > 1:
        return max(times) - min(times) + 1.0
    return float(len(visit))  # sin marcas de tiempo se asume 1 lectura por segundo


def _fix(visits: list[list[GpsReading]], origin: tuple[float, float]) -> VertexFix:
    readings = [r for visit in visits for r in visit]
    return fix_vertex(
        to_enu(readings, origin=origin),
        [sigma_from_accuracy(r.accuracy_m) for r in readings],
        sum(_duration_s(visit) for visit in visits),
    )


def has_fixed_vertices(readings: list[GpsReading]) -> bool:
    """True si el recorrido tiene al menos 3 esquinas fijadas distintas."""
    return len({r.vertex_id for r in readings if r.vertex_id is not None}) >= 3


def stop_and_go_vertices(readings: list[GpsReading], origin: tuple[float, float]) -> StopAndGo:
    """Vértices del polígono a partir de las esquinas fijadas, en el orden en que se visitaron.

    Si la última visita vuelve a la primera esquina, se toma como cierre: se mide la distancia entre
    ambas fijaciones, se promedian (ponderadas por 1/σ²) y el cierre fija el piso de σ de todas.
    """
    visits = _visits(readings)
    closure_visit: list[GpsReading] | None = None
    if len(visits) > 2 and visits[-1][0] == visits[0][0]:
        closure_visit = visits.pop()[1]

    groups: dict[int, list[list[GpsReading]]] = {}
    for vertex_id, visit in visits:
        groups.setdefault(vertex_id, []).append(visit)
    if len(groups) < 3:
        raise GeometryError(f"Solo {len(groups)} esquinas fijadas; se necesitan al menos 3 (EX-05)")

    fixes = [_fix(group, origin) for group in groups.values()]
    rejected = sum(f.rejected for f in fixes)
    closure_m: float | None = None
    closure_consistent: bool | None = None
    floor = 0.0
    if closure_visit is not None:
        first, last = fixes[0], _fix([closure_visit], origin)
        rejected += last.rejected
        closure_m = math.dist(first.point, last.point)
        # d ~ Rayleigh(√(σ₁² + σ₂²)): E[d] = σ·√π cuando σ₁ = σ₂ = σ; P95 = 2,448·√(σ₁² + σ₂²)
        floor = closure_m / math.sqrt(math.pi)
        closure_consistent = closure_m <= RAYLEIGH_P95 * math.hypot(first.sigma_m, last.sigma_m)
        w1, w2 = 1 / first.sigma_m**2, 1 / last.sigma_m**2
        merged = _weighted_mean([first.point, last.point], [w1, w2])
        fixes[0] = VertexFix(merged, 1 / math.sqrt(w1 + w2), first.used + last.used, first.rejected + last.rejected)

    return StopAndGo(
        vertices=[f.point for f in fixes],
        sigmas_m=[max(f.sigma_m, floor) for f in fixes],
        closure_m=closure_m,
        closure_consistent=closure_consistent,
        closure_dominated=any(floor > f.sigma_m for f in fixes),
        rejected=rejected,
    )


def _segment_distance(p: Point, a: Point, b: Point) -> float:
    abx, aby = b[0] - a[0], b[1] - a[1]
    den = abx * abx + aby * aby
    t = 0.0 if den == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * abx + (p[1] - a[1]) * aby) / den))
    return math.hypot(p[0] - a[0] - t * abx, p[1] - a[1] - t * aby)


def track_residual_sigma(track: list[Point], vertices: list[Point], exclude_radius_m: float) -> float:
    """σ empírica de un recorrido continuo: RMS de la distancia de cada lectura a su lado más cercano.

    Se excluyen las lecturas cerca de los vértices (el redondeo de la esquina no es ruido). Se usa como
    σ de cada vértice cuando no hay esquinas fijadas: es conservadora, porque el vértice sale de ajustar
    rectas a muchas lecturas.
    """
    n = len(vertices)
    residuals = [
        min(_segment_distance(p, vertices[i], vertices[(i + 1) % n]) for i in range(n))
        for p in track
        if min(math.dist(p, v) for v in vertices) >= exclude_radius_m
    ]
    if not residuals:
        return MIN_SIGMA_M
    return max(MIN_SIGMA_M, math.sqrt(statistics.fmean(r * r for r in residuals)))
