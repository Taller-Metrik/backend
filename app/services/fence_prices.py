"""Precio unitario de las partidas del cerco a partir del catálogo de materiales (RF-23, RF-27).

Cada partida se costea con su receta de materiales (cantidad por unidad de partida, en la unidad de contenido del
catálogo: kg, m, und), con las proporciones usuales en obra (rendimientos tipo CAPECO). El presupuesto es **solo de
materiales**: el trabajo (trazo, excavación, eliminación, encofrado) se muestra como desglose sin precio.
"""

from dataclasses import dataclass

from app.services.fence import STEEL_KG_M, FenceParams
from app.services.price_catalog import CATALOG_BY_KEY

STAPLES_PER_KG = 170.0  # grapas 1" × 9 (BWG)
CEMENT_KG_PER_BAG = 42.5
SAND_KG_M3 = 1600.0  # arena gruesa suelta
STONE_KG_M3 = 1500.0  # piedra chancada / grande suelta

# Materiales por m³ de mezcla: (bolsas de cemento, m³ de arena gruesa, m³ de piedra)
_MORTAR_1_4 = (8.9, 1.00, 0.0)
_CONCRETE_175 = (8.43, 0.54, 0.55)
# Hormigón ≈ mitad arena gruesa, mitad piedra; la piedra grande/mediana se costea como piedra chancada
_FOOTING_1_10_PG30 = (2.9, 0.83 / 2, 0.83 / 2 + 0.48)
_PLINTH_1_8_PM25 = (3.7, 0.86 / 2, 0.86 / 2 + 0.36)


@dataclass(frozen=True)
class CatalogPrice:
    price: float  # por unidad de venta
    source: str  # store | user


def _mix(per_m3: tuple[float, float, float], m3: float = 1.0) -> dict[str, float]:
    bags, sand_m3, stone_m3 = per_m3
    out = {"cement_bag": bags * CEMENT_KG_PER_BAG * m3, "sand_bag": sand_m3 * SAND_KG_M3 * m3}
    if stone_m3:
        out["stone_bag"] = stone_m3 * STONE_KG_M3 * m3
    return out


def recipes(p: FenceParams) -> dict[str, dict[str, float]]:
    """Material del catálogo (en su unidad de contenido) por unidad de cada partida presupuestable."""
    wall = {"brick_kk18": p.bricks_per_m2 * (1 + p.brick_waste), **_mix(_MORTAR_1_4, p.mortar_m3_per_m2)}
    return {
        # Alambre de púas
        "posts_total": {"pine_post": 1.0},
        "braces": {"pine_post": 1.0},
        "wire_rolls": {"barbed_wire_roll": p.roll_m},
        "staples": {"staples_bag": 1 / STAPLES_PER_KG},
        "concrete_m3": _mix(_FOOTING_1_10_PG30),  # concreto ciclópeo de los hoyos
        # Muro de ladrillo
        "wall_m2": wall,
        "columns_concrete_m3": _mix(_CONCRETE_175),
        "beam_concrete_m3": _mix(_CONCRETE_175),
        "footing_m3": _mix(_FOOTING_1_10_PG30),
        "plinth_m3": _mix(_PLINTH_1_8_PM25),
        "steel_kg": {"rebar_3_8": 1 / STEEL_KG_M["3/8"]},  # los estribos de 1/4" se costean al mismo S/ por kg
    }


def unit_prices(
    item_keys: set[str], catalog: dict[str, CatalogPrice], params: FenceParams
) -> dict[str, tuple[float, str]]:
    """Precio unitario y origen («user» si algún material tiene precio propio) de cada partida con receta completa."""
    out: dict[str, tuple[float, str]] = {}
    for key, recipe in recipes(params).items():
        if key not in item_keys or any(m not in catalog for m in recipe):
            continue
        price = sum(qty * catalog[m].price / CATALOG_BY_KEY[m].content for m, qty in recipe.items())
        source = "user" if any(catalog[m].source == "user" for m in recipe) else "store"
        out[key] = (round(price, 4), source)
    return out
