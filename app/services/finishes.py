"""Metrado de acabados de un ambiente interior (CU-07, RF-22).

Reglas de práctica en Perú (revisadas por ingeniería civil), editables en `FinishParams`:

- Vanos: se descuentan del tarrajeo y la pintura si miden más de 0,25 m² (Norma Técnica de Metrados) y se
  suman sus derrames (espesor del muro × [puerta: 2h + a; ventana: 2h + 2a]).
- Tarrajeo de muros (una cara): mortero 1:5, e = 1,5 cm + 10 % → 0,0165 m³/m²; por m³ de mortero 7,4 bolsas
  de cemento y 1,05 m³ de arena fina (1 m³ ≈ 39 sacos de 40 kg).
- Pintura látex: 2 manos a 32 m²/galón por mano + 1 mano de imprimante a 28 m²/galón; muros y cielo raso.
- Porcelanato: 5 % de desperdicio; pegamento 6 kg/m² (bolsa de 25 kg); fragua 0,4 kg/m²; cajas de 1,44 m².
- Contrazócalo del mismo porcelanato, h = 0,10 m, +10 % por cortes; se descuentan los anchos de las puertas.

Las partidas en m² y m son **mano de obra** (precio del usuario); los insumos usan las claves del catálogo
de precios (`price_catalog`), así el presupuesto toma el precio de la tienda o el propio del usuario.
"""

import math
from dataclasses import dataclass, field
from typing import Literal

from app.services.fence import TakeoffItem
from app.services.geometry import GeometryError

_PURCHASE_UNITS = {"und", "bolsa", "saco", "caja", "galón", "balde", "kg"}  # se compran enteros


@dataclass(frozen=True)
class Opening:
    wall: int  # índice del muro (0 = del vértice 1 al 2)
    kind: Literal["door", "window"]
    width_m: float
    height_m: float


@dataclass(frozen=True)
class FinishParams:
    height_m: float = 2.50
    wall_thickness_m: float = 0.15  # para los derrames (ladrillo en soga + tarrajeo)
    min_deducted_opening_m2: float = 0.25
    mortar_m3_per_m2: float = 0.015 * 1.10  # tarrajeo e = 1,5 cm + 10 % de desperdicio
    cement_bags_per_m3: float = 7.4  # mortero 1:5
    sand_m3_per_m3: float = 1.05
    sand_bags_per_m3: float = 39.0  # sacos de 40 kg (arena suelta ≈ 1550 kg/m³)
    paint_coats: int = 2
    paint_m2_per_gal: float = 32.0
    primer_m2_per_gal: float = 28.0
    primer_gal_per_unit: float = 4.0
    tile_waste: float = 0.05
    tile_box_m2: float = 1.44
    adhesive_kg_m2: float = 6.0
    adhesive_bag_kg: float = 25.0
    grout_kg_m2: float = 0.4
    baseboard_height_m: float = 0.10
    baseboard_waste: float = 0.10


@dataclass(frozen=True)
class FinishTakeoff:
    items: list[TakeoffItem]
    assumptions: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _n(value: float, decimals: int = 2) -> str:
    return f"{value:.{decimals}f}".replace(".", ",")


def _validate(walls: list[float], openings: list[Opening], p: FinishParams) -> None:
    if len(walls) < 3 or any(not math.isfinite(w) or w <= 0 for w in walls):
        raise GeometryError("El ambiente necesita al menos 3 muros de longitud mayor que 0 (EX-05)")
    for i, o in enumerate(openings, start=1):
        if not 0 <= o.wall < len(walls):
            raise GeometryError(f"El vano {i} está en el muro {o.wall + 1}, pero el ambiente tiene {len(walls)} muros")
        if o.height_m > p.height_m:
            raise GeometryError(f"El vano {i} ({_n(o.height_m)} m) es más alto que el ambiente ({_n(p.height_m)} m) (EX-08)")
    for w, length in enumerate(walls):
        widths = sum(o.width_m for o in openings if o.wall == w)
        if widths > length:
            raise GeometryError(f"Los vanos del muro {w + 1} ({_n(widths)} m) no caben en el muro ({_n(length)} m) (EX-08)")


def _item(key: str, description: str, unit: str, value: float, priceable: bool = True) -> TakeoffItem:
    """Partida sin rango (no depende del GPS): cantidad = mínimo = máximo; se compra redondeado hacia arriba."""
    if unit in _PURCHASE_UNITS:
        value = float(math.ceil(value - 1e-9))
        return TakeoffItem(key, description, unit, value, value, value, value, priceable)
    value = round(value, 2)
    return TakeoffItem(key, description, unit, value, value, value, value, priceable)


def finishes_takeoff(area_m2: float, walls: list[float], params: FinishParams, openings: list[Opening]) -> FinishTakeoff:
    """Mano de obra (desglose, sin precio) e insumos (con clave del catálogo, presupuestables) para revestir un ambiente."""
    _validate(walls, openings, params)
    p, h = params, params.height_m
    perimeter = sum(walls)
    deducted = [o for o in openings if o.width_m * o.height_m > p.min_deducted_opening_m2]
    openings_m2 = sum(o.width_m * o.height_m for o in deducted)
    reveals_m2 = sum(
        (2 * o.height_m + (o.width_m if o.kind == "door" else 2 * o.width_m)) * p.wall_thickness_m for o in deducted
    )
    plaster_m2 = perimeter * h - openings_m2 + reveals_m2
    baseboard_m = perimeter - sum(o.width_m for o in openings if o.kind == "door")
    baseboard_m2 = baseboard_m * p.baseboard_height_m
    painted_m2 = plaster_m2 + area_m2
    mortar_m3 = plaster_m2 * p.mortar_m3_per_m2

    items = [
        _item("floor_m2", "Piso de porcelanato (mano de obra)", "m²", area_m2, priceable=False),
        _item("baseboard_m", "Contrazócalo de porcelanato h = 0,10 m (mano de obra)", "m", baseboard_m, priceable=False),
        _item("plaster_m2", "Tarrajeo de muros interiores 1:5 (mano de obra)", "m²", plaster_m2, priceable=False),
        _item("wall_paint_m2", f"Pintura látex en muros, {p.paint_coats} manos (mano de obra)", "m²", plaster_m2, priceable=False),
        _item("ceiling_paint_m2", f"Pintura látex en cielo raso, {p.paint_coats} manos (mano de obra)", "m²", area_m2, priceable=False),
        _item("porcelain_box", "Porcelanato (cajas)", "caja",
              (area_m2 * (1 + p.tile_waste) + baseboard_m2 * (1 + p.baseboard_waste)) / p.tile_box_m2),
        _item("tile_adhesive_bag", "Pegamento para porcelanato (bolsas de 25 kg)", "bolsa",
              (area_m2 + baseboard_m2) * p.adhesive_kg_m2 / p.adhesive_bag_kg),
        _item("grout_kg", "Fragua", "kg", area_m2 * p.grout_kg_m2),
        _item("cement_bag", "Cemento para tarrajeo (bolsas de 42,5 kg)", "bolsa", mortar_m3 * p.cement_bags_per_m3),
        _item("fine_sand_bag", "Arena fina para tarrajeo (sacos de 40 kg)", "saco",
              mortar_m3 * p.sand_m3_per_m3 * p.sand_bags_per_m3),
        _item("paint_gallon", "Pintura látex (galones)", "galón", painted_m2 * p.paint_coats / p.paint_m2_per_gal),
        _item("primer_4gal", "Imprimante (baldes de 4 galones)", "balde",
              painted_m2 / p.primer_m2_per_gal / p.primer_gal_per_unit),
    ]
    assumptions = [
        f"Altura del ambiente {_n(h)} m; muros de {_n(p.wall_thickness_m)} m de espesor para los derrames.",
        "Se descuentan los vanos de más de 0,25 m² y se suman sus derrames (Norma Técnica de Metrados).",
        "Tarrajeo de una cara con mortero 1:5, e = 1,5 cm + 10 %: 7,4 bolsas de cemento y 1,05 m³ de arena fina por m³.",
        (f"Pintura látex: {p.paint_coats} manos a {_n(p.paint_m2_per_gal, 0)} m²/galón; imprimante a "
         f"{_n(p.primer_m2_per_gal, 0)} m²/galón; muros y cielo raso."),
        (f"Porcelanato con {p.tile_waste:.0%} de desperdicio, cajas de {_n(p.tile_box_m2)} m²; pegamento "
         f"{_n(p.adhesive_kg_m2, 0)} kg/m²; fragua {_n(p.grout_kg_m2, 1)} kg/m²."),
        "Contrazócalo del mismo porcelanato, h = 0,10 m, +10 % por cortes; sin el ancho de las puertas.",
    ]
    notes = [
        "Metrado referencial a partir del plano medido; verificar medidas con wincha antes de comprar.",
        "Presupuesto solo de materiales: la mano de obra (m² y m) se muestra como desglose sin precio.",
    ]
    return FinishTakeoff(items=items, assumptions=assumptions, notes=notes)
