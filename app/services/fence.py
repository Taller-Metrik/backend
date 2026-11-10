"""Metrado de cerco perimétrico (CU-09, RF-27).

Reglas de práctica en Perú (revisadas por ingeniería civil), todas editables en `FenceParams`:

- **Alambre de púas:** postes cada 3 m; esquineros con 2 pies de amigo; un poste de refuerzo (2 pies de
  amigo) cada ~50 m de tramo recto; 2 postes reforzados por portón (1 pie de amigo cada uno); 4 hilos con
  5 % de desperdicio en rollos de 200 m; grapas = postes × hilos × 1,1; hoyo 0,30 × 0,30 × 0,60 m y
  ≈ 0,05 m³ de concreto ciclópeo por poste.
- **Muro de ladrillo:** altura 2,40 m en soga (e = 0,13 m); columnas 0,25 × 0,13 m cada 3 m, en esquinas y
  a cada lado de un portón; viga solera 0,15 × 0,20 m; ladrillo KK 18 huecos 39 und/m² + 5 %; mortero
  0,025 m³/m²; cimiento corrido 0,40 × 0,70 m; sobrecimiento 0,15 × 0,30 m; esponjamiento 25 %.

La incertidumbre del perímetro (U95) se lleva a un rango: cada lado se escala por (P ± U)/P, se rehace el
metrado y se recomienda comprar el máximo (redondeado hacia arriba).
"""

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from app.services.geometry import GeometryError

_EPS = 1e-9
STEEL_3_8_KG_M = 0.56  # acero corrugado Ø 3/8"
STEEL_1_4_KG_M = 0.25  # acero liso Ø 1/4" (estribos)


@dataclass(frozen=True)
class Gate:
    side: int  # índice del lado (0 = del vértice 1 al 2)
    width_m: float


@dataclass(frozen=True)
class FenceParams:
    kind: Literal["wire", "brick"]
    # Alambre de púas
    post_spacing_m: float = 3.0
    brace_every_m: float = 50.0
    strands: int = 4
    wire_waste: float = 0.05
    roll_m: float = 200.0
    staples_factor: float = 1.1
    hole_m3: float = 0.30 * 0.30 * 0.60
    concrete_per_post_m3: float = 0.05
    # Muro de ladrillo
    wall_height_m: float = 2.40
    column_spacing_m: float = 3.0
    column_width_m: float = 0.25
    column_depth_m: float = 0.13
    beam_section_m2: float = 0.15 * 0.20
    beam_height_m: float = 0.20
    bricks_per_m2: float = 39.0
    brick_waste: float = 0.05
    mortar_m3_per_m2: float = 0.025
    footing_section_m2: float = 0.40 * 0.70
    plinth_section_m2: float = 0.15 * 0.30
    plinth_height_m: float = 0.30
    swell: float = 0.25


@dataclass(frozen=True)
class TakeoffItem:
    key: str
    description: str
    unit: str
    quantity: float  # con el perímetro medido
    min: float  # con el perímetro − U95
    max: float  # con el perímetro + U95
    purchase: float  # lo que conviene comprar: el máximo redondeado hacia arriba


@dataclass(frozen=True)
class FenceTakeoff:
    kind: str
    perimeter_m: float
    perimeter_u95_m: float | None
    net_length_m: float  # perímetro menos portones
    items: list[TakeoffItem]
    assumptions: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# (descripción, unidad, valor) por clave; las unidades "und" y "rollo" son enteras
_Quantities = dict[str, tuple[str, str, float]]
_COUNT_UNITS = {"und", "rollo"}


def _segments(sides: list[float], gates: list[Gate]) -> list[float]:
    """Tramos continuos de cerco: cada portón divide su lado (se asume repartido en partes iguales)."""
    out: list[float] = []
    for i, length in enumerate(sides):
        widths = [g.width_m for g in gates if g.side == i]
        n = len(widths) + 1
        out += [max(0.0, (length - sum(widths)) / n)] * n
    return out


def _between(segment: float, spacing: float) -> int:
    """Apoyos intermedios en un tramo (sin contar los extremos)."""
    return max(0, math.ceil(segment / spacing - _EPS) - 1) if segment > 0 else 0


def _wire(sides: list[float], gates: list[Gate], p: FenceParams) -> _Quantities:
    segs = _segments(sides, gates)
    intermediate = sum(_between(s, p.post_spacing_m) for s in segs)
    brace = min(intermediate, sum(_between(s, p.brace_every_m) for s in segs))
    corner, gate_posts = len(sides), 2 * len(gates)
    total = intermediate + corner + gate_posts  # los de refuerzo están entre los intermedios
    net = sum(sides) - sum(g.width_m for g in gates)
    wire_m = net * p.strands * (1 + p.wire_waste)
    return {
        "layout_m": ("Trazo y replanteo", "m", sum(sides)),
        "posts_line": ("Postes de línea", "und", intermediate - brace),
        "posts_brace": ("Postes de refuerzo (cada ~50 m)", "und", brace),
        "posts_corner": ("Postes esquineros", "und", corner),
        "posts_gate": ("Postes de portón (reforzados)", "und", gate_posts),
        "posts_total": ("Postes en total", "und", total),
        "braces": ("Pies de amigo", "und", 2 * corner + 2 * brace + gate_posts),
        "wire_m": (f"Alambre de púas ({p.strands} hilos, +{p.wire_waste:.0%} desperdicio)", "m", wire_m),
        "wire_rolls": (f"Rollos de alambre de {p.roll_m:.0f} m", "rollo", math.ceil(wire_m / p.roll_m - _EPS)),
        "staples": ("Grapas", "und", math.ceil(total * p.strands * p.staples_factor - _EPS)),
        "excavation_m3": ("Excavación de hoyos", "m³", total * p.hole_m3),
        "concrete_m3": ("Concreto ciclópeo para postes", "m³", total * p.concrete_per_post_m3),
        "gates": ("Portones", "und", len(gates)),
    }


def _brick(sides: list[float], gates: list[Gate], p: FenceParams) -> _Quantities:
    segs = _segments(sides, gates)
    columns = len(sides) + 2 * len(gates) + sum(_between(s, p.column_spacing_m) for s in segs)
    net = sum(sides) - sum(g.width_m for g in gates)
    h = p.wall_height_m
    wall_m2 = max(0.0, net - columns * p.column_width_m) * (h - p.beam_height_m)
    stirrups = math.ceil(h / 0.20) + 1
    steel = (columns * (4 * (h + 0.60) * STEEL_3_8_KG_M + stirrups * 0.70 * STEEL_1_4_KG_M)
             + net * 1.1 * 4 * STEEL_3_8_KG_M)
    excavation = net * p.footing_section_m2
    formwork = net * p.plinth_height_m * 2 + columns * 2 * p.column_width_m * h + net * p.beam_height_m * 2
    return {
        "layout_m": ("Trazo y replanteo", "m", sum(sides)),
        "excavation_m3": ("Excavación de zanjas", "m³", excavation),
        "disposal_m3": (f"Eliminación de material (+{p.swell:.0%} esponjamiento)", "m³", excavation * (1 + p.swell)),
        "footing_m3": ("Cimiento corrido 1:10 + 30 % PG", "m³", net * p.footing_section_m2),
        "plinth_m3": ("Sobrecimiento 1:8 + 25 % PM", "m³", net * p.plinth_section_m2),
        "columns": ("Columnas de confinamiento", "und", columns),
        "columns_concrete_m3": (
            "Concreto f'c = 175 kg/cm² en columnas", "m³", columns * p.column_width_m * p.column_depth_m * h
        ),
        "beam_concrete_m3": ("Concreto f'c = 175 kg/cm² en viga solera", "m³", net * p.beam_section_m2),
        "steel_kg": ("Acero (columnas y viga solera)", "kg", steel),
        "formwork_m2": ("Encofrado (sobrecimiento, columnas y viga)", "m²", formwork),
        "wall_m2": ("Muro de ladrillo en soga", "m²", wall_m2),
        "bricks": (
            f"Ladrillo KK 18 huecos (+{p.brick_waste:.0%})", "und",
            math.ceil(wall_m2 * p.bricks_per_m2 * (1 + p.brick_waste) - _EPS),
        ),
        "mortar_m3": ("Mortero 1:4", "m³", wall_m2 * p.mortar_m3_per_m2),
        "gates": ("Portones", "und", len(gates)),
    }


def _round_up(value: float, unit: str) -> float:
    return float(math.ceil(value - _EPS)) if unit in _COUNT_UNITS else math.ceil(value * 100 - _EPS) / 100


def _validate(sides: list[float], gates: list[Gate]) -> None:
    if len(sides) < 3:
        raise GeometryError("El terreno necesita al menos 3 lados (EX-05)")
    for g in gates:
        if not 0 <= g.side < len(sides):
            raise GeometryError(f"El portón está en el lado {g.side + 1}, pero el terreno tiene {len(sides)} lados")
    for i, length in enumerate(sides):
        widths = sum(g.width_m for g in gates if g.side == i)
        if widths >= length:
            raise GeometryError(f"Los portones del lado {i + 1} ({widths:.2f} m) no caben en el lado ({length:.2f} m)")


def _n(value: float, decimals: int = 2) -> str:
    return f"{value:.{decimals}f}".replace(".", ",")


def _texts(params: FenceParams, gates: list[Gate], u95: float | None) -> tuple[list[str], list[str]]:
    """Supuestos usados y advertencias que debe mostrar el reporte."""
    if params.kind == "wire":
        assumptions = [
            f"Postes cada {_n(params.post_spacing_m)} m; refuerzo cada {_n(params.brace_every_m, 0)} m de tramo recto.",
            "Esquineros y refuerzos con 2 pies de amigo; postes de portón con 1.",
            f"{params.strands} hilos con {params.wire_waste:.0%} de desperdicio; rollos de {params.roll_m:.0f} m.",
            f"Hoyo de {_n(params.hole_m3, 3)} m³ y {_n(params.concrete_per_post_m3)} m³ de concreto ciclópeo por poste.",
        ]
    else:
        assumptions = [
            f"Muro de {_n(params.wall_height_m)} m de alto en soga; columnas cada {_n(params.column_spacing_m)} m.",
            f"Ladrillo KK 18 huecos: {params.bricks_per_m2:.0f} und/m² + {params.brick_waste:.0%}; mortero 1:4.",
            "Cimiento corrido 0,40 × 0,70 m; sobrecimiento 0,15 × 0,30 m; viga solera 0,15 × 0,20 m.",
        ]
    if gates:
        assumptions.append("Cada portón se ubica al centro de su lado.")
    if u95:
        notes = [(f"Metrado referencial obtenido con GPS de celular (U95 del perímetro = ±{_n(u95, 1)} m); "
                  "verificar con wincha antes de comprar o replantear.")]
    else:
        notes = ["Metrado referencial calculado sin incertidumbre del perímetro; verificar con wincha antes de comprar."]
    notes += ["La columna «comprar» usa el máximo del rango, redondeado hacia arriba.", "No verifica linderos legales del predio."]
    if params.kind == "brick":
        notes.append("No incluye estudio de suelos ni diseño estructural: el muro de albañilería se rige por la norma E.070.")
    return assumptions, notes


def fence_takeoff(
    sides: list[float],
    params: FenceParams,
    *,
    gates: list[Gate] | None = None,
    perimeter_u95_m: float | None = None,
) -> FenceTakeoff:
    """Metrado del cerco con su rango de compra según la incertidumbre del perímetro."""
    gates = gates or []
    _validate(sides, gates)
    compute: Callable[[list[float], list[Gate], FenceParams], _Quantities] = _wire if params.kind == "wire" else _brick
    perimeter = sum(sides)
    u = perimeter_u95_m or 0.0
    nominal = compute(sides, gates, params)
    low = compute([s * (perimeter - u) / perimeter for s in sides], gates, params)
    high = compute([s * (perimeter + u) / perimeter for s in sides], gates, params)

    items = []
    for key, (description, unit, value) in nominal.items():
        def fmt(x: float, unit: str = unit) -> float:
            return float(x) if unit in _COUNT_UNITS else round(x, 2)

        hi = high[key][2]
        items.append(TakeoffItem(key, description, unit, fmt(value), fmt(low[key][2]), fmt(hi), _round_up(hi, unit)))

    assumptions, notes = _texts(params, gates, perimeter_u95_m)
    return FenceTakeoff(
        kind=params.kind,
        perimeter_m=perimeter,
        perimeter_u95_m=perimeter_u95_m,
        net_length_m=perimeter - sum(g.width_m for g in gates),
        items=items,
        assumptions=assumptions,
        notes=notes,
    )
