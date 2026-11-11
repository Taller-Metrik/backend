"""Metrado de cerco perimétrico (CU-09, RF-27).

Reglas de práctica en Perú (revisadas por ingeniería civil), todas editables en `FenceParams`:

- **Alambre de púas:** postes cada 3 m; esquineros con 2 pies de amigo; un poste de refuerzo (2 pies de
  amigo) cada ~50 m de tramo recto; 2 postes reforzados por portón (1 pie de amigo cada uno); postes y pies
  de amigo llevan hoyo de 0,30 × 0,30 × 0,60 m y ≈ 0,05 m³ de concreto ciclópeo; 4 hilos con 5 % de
  desperdicio en rollos de 200 m; grapas = postes × hilos × 1,1.
- **Muro de ladrillo:** altura medida desde el terreno natural hasta lo alto de la viga solera (2,40 m);
  muro en soga, columnas y solera del mismo ancho (0,13 m); columnas 0,25 × 0,13 m cada 3 m y en esquinas,
  hasta la solera (sin contar dos veces el nudo); columnas de portón reforzadas 0,25 × 0,25 m con 4 Ø 1/2";
  ladrillo KK 18 huecos 39 und/m² + 5 % sobre la altura de ladrillo (altura − solera − sobrecimiento
  visible); mortero 0,025 m³/m²; cimiento corrido 0,40 × 0,70 m (no va bajo el portón); sobrecimiento
  0,15 × 0,30 m; esponjamiento 25 %.

La incertidumbre del perímetro (U95) se lleva a un rango: el tramo cercado de cada lado (lado − portones)
se escala por (P ± U)/P, se rehace el metrado y se recomienda comprar el máximo (redondeado hacia arriba).
"""

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from app.services.geometry import GeometryError

STEEL_KG_M = {"1/4": 0.25, "3/8": 0.56, "1/2": 0.994}  # peso del acero por metro según el diámetro


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
    concrete_per_hole_m3: float = 0.05
    # Muro de ladrillo
    wall_height_m: float = 2.40  # desde el terreno natural hasta lo alto de la solera
    wall_thickness_m: float = 0.13  # muro en soga; columnas y solera del mismo ancho
    column_spacing_m: float = 3.0
    column_width_m: float = 0.25
    gate_column_width_m: float = 0.25  # columnas de portón 0,25 × 0,25 (cargan las bisagras)
    beam_height_m: float = 0.20
    plinth_visible_m: float = 0.10  # sobrecimiento sobre el terreno
    plinth_section_m2: float = 0.15 * 0.30
    plinth_height_m: float = 0.30
    footing_section_m2: float = 0.40 * 0.70
    bricks_per_m2: float = 39.0
    brick_waste: float = 0.05
    mortar_m3_per_m2: float = 0.025
    swell: float = 0.25
    # Acero
    bars_per_element: int = 4
    column_anchorage_m: float = 0.60  # anclaje de las barras de columna en el cimiento
    stirrup_spacing_m: float = 0.20
    column_stirrup_m: float = 0.70
    beam_stirrup_spacing_m: float = 0.25
    beam_stirrup_m: float = 0.60
    lap_factor: float = 1.10  # traslapes de las barras de la solera


@dataclass(frozen=True)
class TakeoffItem:
    key: str
    description: str
    unit: str
    quantity: float  # con el perímetro medido
    min: float  # con el perímetro − U95
    max: float  # con el perímetro + U95
    purchase: float  # lo que conviene comprar: el máximo redondeado hacia arriba
    priceable: bool = True  # False = desglose informativo (no se presupuesta, ya está en otra partida)


@dataclass(frozen=True)
class FenceTakeoff:
    kind: str
    perimeter_m: float
    perimeter_u95_m: float | None
    net_length_m: float  # perímetro menos portones
    items: list[TakeoffItem]
    assumptions: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# (descripción, unidad, valor, presupuestable) por clave; "und" y "rollo" son enteras
_Quantities = dict[str, tuple[str, str, float, bool]]
_COUNT_UNITS = {"und", "rollo"}
_INFO = False  # partida informativa


def _between(segment: float, spacing: float) -> int:
    """Apoyos intermedios en un tramo (sin contar los extremos)."""
    return max(0, math.ceil(segment / spacing - 1e-9) - 1) if segment > 0 else 0


def _segments(fenced: list[float], gates: list[Gate]) -> list[float]:
    """Tramos continuos: cada portón divide su lado (se asume repartido en partes iguales)."""
    out: list[float] = []
    for i, length in enumerate(fenced):
        n = sum(1 for g in gates if g.side == i) + 1
        out += [length / n] * n
    return out


def _wire(fenced: list[float], gates: list[Gate], p: FenceParams) -> _Quantities:
    segs = _segments(fenced, gates)
    intermediate = sum(_between(s, p.post_spacing_m) for s in segs)
    brace = min(intermediate, sum(_between(s, p.brace_every_m) for s in segs))
    corner, gate_posts = len(fenced), 2 * len(gates)
    total = intermediate + corner + gate_posts  # los de refuerzo están entre los intermedios
    braces = 2 * corner + 2 * brace + gate_posts
    net = sum(fenced)
    wire_m = net * p.strands * (1 + p.wire_waste)
    holes = total + braces  # los pies de amigo también se entierran
    return {
        "layout_m": ("Trazo y replanteo (trabajo)", "m", net + sum(g.width_m for g in gates), _INFO),
        "posts_line": ("Postes de línea", "und", intermediate - brace, _INFO),
        "posts_brace": ("Postes de refuerzo (cada ~50 m)", "und", brace, _INFO),
        "posts_corner": ("Postes esquineros", "und", corner, _INFO),
        "posts_gate": ("Postes de portón (reforzados)", "und", gate_posts, _INFO),
        "posts_total": ("Postes en total", "und", total, True),
        "braces": ("Pies de amigo", "und", braces, True),
        "wire_m": (f"Alambre de púas ({p.strands} hilos, +{p.wire_waste:.0%} desperdicio)", "m", wire_m, _INFO),
        "wire_rolls": (f"Rollos de alambre de {p.roll_m:.0f} m", "rollo", math.ceil(wire_m / p.roll_m - 1e-9), True),
        "staples": ("Grapas", "und", math.ceil(total * p.strands * p.staples_factor - 1e-9), True),
        "excavation_m3": ("Excavación de hoyos (trabajo)", "m³", holes * p.hole_m3, _INFO),
        "concrete_m3": ("Concreto ciclópeo (postes y pies de amigo)", "m³", holes * p.concrete_per_hole_m3, True),
        "gates": ("Portones", "und", len(gates), True),
    }


def _brick(fenced: list[float], gates: list[Gate], p: FenceParams) -> _Quantities:
    segs = _segments(fenced, gates)
    columns = len(fenced) + sum(_between(s, p.column_spacing_m) for s in segs)
    gate_columns = 2 * len(gates)
    net = sum(fenced)
    t, h = p.wall_thickness_m, p.wall_height_m
    column_h = h - p.beam_height_m  # hasta la solera: el nudo se cuenta una sola vez
    brick_h = h - p.beam_height_m - p.plinth_visible_m
    wall_m2 = max(0.0, net - columns * p.column_width_m - gate_columns * p.gate_column_width_m) * brick_h
    bar_m = p.bars_per_element * (h + p.column_anchorage_m)
    stirrups = (math.ceil(column_h / p.stirrup_spacing_m) + 1) * p.column_stirrup_m * STEEL_KG_M["1/4"]
    steel = (
        columns * (bar_m * STEEL_KG_M["3/8"] + stirrups)
        + gate_columns * (bar_m * STEEL_KG_M["1/2"] + stirrups)
        + net * p.lap_factor * p.bars_per_element * STEEL_KG_M["3/8"]
        + math.ceil(net / p.beam_stirrup_spacing_m) * p.beam_stirrup_m * STEEL_KG_M["1/4"]
    )
    excavation = net * p.footing_section_m2  # el cimiento corrido no va bajo el portón
    formwork = (
        net * p.plinth_height_m * 2
        + (columns * p.column_width_m + gate_columns * p.gate_column_width_m) * 2 * column_h
        + net * p.beam_height_m * 2
    )
    return {
        "layout_m": ("Trazo y replanteo (trabajo)", "m", net + sum(g.width_m for g in gates), _INFO),
        "excavation_m3": ("Excavación de zanjas (trabajo)", "m³", excavation, _INFO),
        "disposal_m3": (
            f"Eliminación de material (+{p.swell:.0%} esponjamiento, trabajo)", "m³", excavation * (1 + p.swell), _INFO
        ),
        "footing_m3": ("Cimiento corrido 1:10 + 30 % PG", "m³", excavation, True),
        "plinth_m3": ("Sobrecimiento 1:8 + 25 % PM", "m³", net * p.plinth_section_m2, True),
        "columns": ("Columnas de confinamiento 0,25 × 0,13 m", "und", columns, _INFO),
        "columns_gate": ("Columnas de portón 0,25 × 0,25 m (4 Ø 1/2\")", "und", gate_columns, _INFO),
        "columns_concrete_m3": (
            "Concreto f'c = 175 kg/cm² en columnas", "m³",
            (columns * p.column_width_m * t + gate_columns * p.gate_column_width_m ** 2) * column_h, True,
        ),
        "beam_concrete_m3": ("Concreto f'c = 175 kg/cm² en viga solera", "m³", net * t * p.beam_height_m, True),
        "steel_kg": ("Acero (columnas, solera y estribos)", "kg", steel, True),
        "formwork_m2": ("Encofrado (sobrecimiento, columnas y viga; trabajo)", "m²", formwork, _INFO),
        "wall_m2": ("Muro de ladrillo en soga", "m²", wall_m2, True),
        "bricks": (
            f"Ladrillo KK 18 huecos (+{p.brick_waste:.0%})", "und",
            math.ceil(wall_m2 * p.bricks_per_m2 * (1 + p.brick_waste) - 1e-9), _INFO,
        ),
        "mortar_m3": ("Mortero 1:4", "m³", wall_m2 * p.mortar_m3_per_m2, _INFO),
        "gates": ("Portones", "und", len(gates), True),
    }


def _round_up(value: float, unit: str) -> float:
    """Redondeo hacia arriba (enteros o centésimas) con tolerancia relativa al tamaño del número."""
    eps = max(1e-9, abs(value) * 1e-12)
    return float(math.ceil(value - eps)) if unit in _COUNT_UNITS else math.ceil(value * 100 - eps * 100) / 100


def _fmt(value: float, unit: str) -> float:
    return float(value) if unit in _COUNT_UNITS else round(value, 2)


def _validate(sides: list[float], gates: list[Gate]) -> None:
    if len(sides) < 3:
        raise GeometryError("El terreno necesita al menos 3 lados (EX-05)")
    if any(not math.isfinite(s) or s <= 0 for s in sides):
        raise GeometryError("Todos los lados del terreno deben tener longitud mayor que 0 (EX-05)")
    for g in gates:
        if not 0 <= g.side < len(sides):
            raise GeometryError(f"El portón está en el lado {g.side + 1}, pero el terreno tiene {len(sides)} lados")
    for i, length in enumerate(sides):
        widths = sum(g.width_m for g in gates if g.side == i)
        if widths >= length:
            raise GeometryError(f"Los portones del lado {i + 1} ({widths:.2f} m) no caben en el lado ({length:.2f} m)")


def _n(value: float, decimals: int = 2) -> str:
    return f"{value:.{decimals}f}".replace(".", ",")


def _texts(params: FenceParams, gates: list[Gate], u95: float | None, perimeter: float) -> tuple[list[str], list[str]]:
    """Supuestos usados y advertencias que debe mostrar el reporte."""
    if params.kind == "wire":
        assumptions = [
            f"Postes cada {_n(params.post_spacing_m)} m; refuerzo cada {_n(params.brace_every_m, 0)} m de tramo recto.",
            "Esquineros y refuerzos con 2 pies de amigo; postes de portón con 1. Postes y pies de amigo van enterrados.",
            f"{params.strands} hilos con {params.wire_waste:.0%} de desperdicio; rollos de {params.roll_m:.0f} m.",
            f"Hoyo de {_n(params.hole_m3, 3)} m³ y {_n(params.concrete_per_hole_m3)} m³ de concreto ciclópeo por hoyo.",
        ]
    else:
        assumptions = [
            f"Altura de {_n(params.wall_height_m)} m medida desde el terreno natural hasta lo alto de la viga solera.",
            (f"Muro en soga de {_n(params.wall_thickness_m)} m; columnas cada {_n(params.column_spacing_m)} m; "
             "columnas de portón de 0,25 × 0,25 m."),
            f"Ladrillo KK 18 huecos: {params.bricks_per_m2:.0f} und/m² + {params.brick_waste:.0%}; mortero 1:4.",
            "Cimiento corrido 0,40 × 0,70 m (no va bajo el portón); sobrecimiento 0,15 × 0,30 m.",
        ]
    if gates:
        assumptions.append("Cada portón se ubica al centro de su lado.")
    if u95 is not None:
        notes = [(f"Metrado referencial obtenido con GPS de celular (U95 del perímetro = ±{_n(u95, 1)} m); "
                  "verificar con wincha antes de comprar o replantear.")]
        if u95 >= perimeter:
            notes.append("La incertidumbre es mayor que el perímetro: el rango mínimo no es útil; vuelva a medir.")
    else:
        notes = ["Metrado referencial calculado sin incertidumbre del perímetro; verificar con wincha antes de comprar."]
    notes += [
        "La columna «comprar» usa el máximo del rango, redondeado hacia arriba.",
        "Las partidas informativas (desglose) no entran al presupuesto: ya están en su partida total.",
        "No verifica linderos legales del predio.",
    ]
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
    if perimeter_u95_m is not None and (not math.isfinite(perimeter_u95_m) or perimeter_u95_m < 0):
        perimeter_u95_m = None  # incertidumbre inválida: se ignora (la nota lo indica)
    compute: Callable[[list[float], list[Gate], FenceParams], _Quantities] = _wire if params.kind == "wire" else _brick
    perimeter = sum(sides)
    u = perimeter_u95_m or 0.0
    # Solo se escala lo cercado (lado − portones): los portones tienen un ancho fijo
    fenced = [s - sum(g.width_m for g in gates if g.side == i) for i, s in enumerate(sides)]
    nominal = compute(fenced, gates, params)
    low = compute([f * max(0.0, (perimeter - u) / perimeter) for f in fenced], gates, params)
    high = compute([f * (perimeter + u) / perimeter for f in fenced], gates, params)

    items = []
    for key, (description, unit, value, priceable) in nominal.items():
        hi = high[key][2]
        items.append(TakeoffItem(
            key, description, unit, _fmt(value, unit), _fmt(low[key][2], unit), _fmt(hi, unit), _round_up(hi, unit),
            priceable,
        ))

    assumptions, notes = _texts(params, gates, perimeter_u95_m, perimeter)
    return FenceTakeoff(
        kind=params.kind,
        perimeter_m=perimeter,
        perimeter_u95_m=perimeter_u95_m,
        net_length_m=sum(fenced),
        items=items,
        assumptions=assumptions,
        notes=notes,
    )
