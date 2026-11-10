"""Incertidumbre del área y del perímetro de un polígono (RF-21).

Cada vértice i tiene un error gaussiano isótropo e independiente con desviación σᵢ por eje.
Propagación lineal sobre la fórmula de Shoelace, A = ½ Σ (xᵢ·yᵢ₊₁ − xᵢ₊₁·yᵢ):

    ∂A/∂xᵢ = ½ (yᵢ₊₁ − yᵢ₋₁),   ∂A/∂yᵢ = ½ (xᵢ₋₁ − xᵢ₊₁)   ⇒   σ_A² = ¼ Σ σᵢ² · dᵢ²

donde dᵢ es la distancia entre los vecinos i − 1 e i + 1. Para el perímetro, el gradiente respecto
de cada vértice es la diferencia de los vectores unitarios de sus dos lados (uᵢₙ − uₒᵤₜ):

    σ_P² = Σ σᵢ² · |uᵢₙ − uₒᵤₜ|²

Se informa la incertidumbre expandida U = k·σ con k = 2 (≈ 95 %). La fórmula se valida contra
Monte Carlo en las pruebas (BU-67).

Nota: un error común a todos los vértices (todo el polígono desplazado igual) no cambia el área ni el
perímetro; por eso σᵢ debe representar el error *relativo* entre vértices. Usar el error absoluto
da una incertidumbre conservadora.
"""

import math
import random
import statistics
from dataclasses import dataclass

from app.services.geometry import GeometryError, Point, segment_lengths, signed_area

COVERAGE_FACTOR = 2.0  # k = 2 → nivel de confianza ≈ 95 %
# Si la σ sale de una sola muestra (el error de cierre), su propia estimación es incierta:
# se amplía k para mantener la cobertura del 95 %.
CLOSURE_COVERAGE_FACTOR = 2.5


@dataclass(frozen=True)
class PolygonUncertainty:
    area_sigma_m2: float
    area_u95_m2: float
    area_u95_pct: float
    perimeter_sigma_m: float
    perimeter_u95_m: float
    perimeter_u95_pct: float
    k: float


def _area(vertices: list[Point]) -> float:
    return abs(signed_area(vertices))


def _perimeter(vertices: list[Point]) -> float:
    return sum(segment_lengths(vertices))


def _unit(a: Point, b: Point) -> Point:
    """Vector unitario de a hacia b; (0, 0) si los puntos coinciden."""
    d = math.dist(a, b)
    return (0.0, 0.0) if d == 0 else ((b[0] - a[0]) / d, (b[1] - a[1]) / d)


def _check(vertices: list[Point], sigmas_m: list[float]) -> None:
    if len(vertices) < 3:
        raise GeometryError("Se necesitan al menos 3 vértices para estimar la incertidumbre")
    if len(sigmas_m) != len(vertices):
        raise GeometryError("Debe haber una desviación estándar por vértice")


def _pct(u: float, value: float) -> float:
    return 100 * u / value


def polygon_uncertainty(
    vertices: list[Point], sigmas_m: list[float], k: float = COVERAGE_FACTOR
) -> PolygonUncertainty:
    """Incertidumbre analítica del área y del perímetro (propagación lineal de errores)."""
    _check(vertices, sigmas_m)
    n = len(vertices)
    var_area = var_perimeter = 0.0
    for i in range(n):
        prev, cur, nxt = vertices[i - 1], vertices[i], vertices[(i + 1) % n]
        s2 = sigmas_m[i] ** 2
        var_area += s2 * ((nxt[0] - prev[0]) ** 2 + (nxt[1] - prev[1]) ** 2) / 4
        u_in, u_out = _unit(prev, cur), _unit(cur, nxt)
        var_perimeter += s2 * ((u_in[0] - u_out[0]) ** 2 + (u_in[1] - u_out[1]) ** 2)
    sa, sp = math.sqrt(var_area), math.sqrt(var_perimeter)
    area, perimeter = _area(vertices), _perimeter(vertices)
    if area <= 0 or perimeter <= 0:
        raise GeometryError("El polígono no tiene área: no se puede estimar la incertidumbre relativa (EX-05)")
    return PolygonUncertainty(
        area_sigma_m2=sa,
        area_u95_m2=k * sa,
        area_u95_pct=_pct(k * sa, area),
        perimeter_sigma_m=sp,
        perimeter_u95_m=k * sp,
        perimeter_u95_pct=_pct(k * sp, perimeter),
        k=k,
    )


def monte_carlo_uncertainty(
    vertices: list[Point], sigmas_m: list[float], runs: int = 2000, seed: int = 0
) -> tuple[float, float]:
    """σ del área y del perímetro por simulación: perturba cada vértice con su σ y mide la dispersión.

    Sirve para validar la fórmula analítica y para casos con errores no lineales.
    """
    _check(vertices, sigmas_m)
    rng = random.Random(seed)
    areas: list[float] = []
    perimeters: list[float] = []
    for _ in range(runs):
        perturbed = [(x + rng.gauss(0, s), y + rng.gauss(0, s)) for (x, y), s in zip(vertices, sigmas_m, strict=True)]
        areas.append(_area(perturbed))
        perimeters.append(_perimeter(perturbed))
    return statistics.pstdev(areas), statistics.pstdev(perimeters)
