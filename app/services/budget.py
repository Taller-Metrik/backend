"""Presupuesto a partir de un metrado (RF-24): costo directo, gastos generales, utilidad e IGV.

Lo usan el cerco perimétrico (CU-09) y, más adelante, el metrado de acabados (CU-07). Los montos se
redondean a céntimos (ROUND_HALF_UP) en cada paso, como en una hoja de presupuesto.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol

from app.services.geometry import GeometryError

IGV_PCT = 18.0


class PricedItem(Protocol):
    key: str
    description: str
    unit: str
    purchase: float


@dataclass(frozen=True)
class BudgetLine:
    key: str
    description: str
    unit: str
    quantity: float
    unit_price: float
    subtotal: float


@dataclass(frozen=True)
class Budget:
    lines: list[BudgetLine]
    direct_cost: float
    overhead_pct: float
    overhead: float
    profit_pct: float
    profit: float
    subtotal: float
    igv_pct: float
    igv: float
    total: float
    missing_prices: list[str]  # partidas del metrado sin precio (no entran al presupuesto)
    currency: str = "PEN"


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _pct(base: Decimal, pct: float) -> Decimal:
    return _money(base * Decimal(str(pct)) / 100)


def build_budget(
    items: Sequence[PricedItem],
    prices: Mapping[str, float],
    *,
    overhead_pct: float = 10.0,
    profit_pct: float = 5.0,
    igv_pct: float = IGV_PCT,
) -> Budget:
    """Presupuesto con la cantidad a comprar de cada partida × su precio unitario."""
    keys = {i.key for i in items}
    unknown = sorted(set(prices) - keys)
    if unknown:
        raise GeometryError(f"Hay precios para partidas que no existen en el metrado: {', '.join(unknown)}")
    lines: list[BudgetLine] = []
    direct = Decimal(0)
    for item in items:
        if item.key not in prices:
            continue
        price = Decimal(str(prices[item.key]))
        subtotal = _money(Decimal(str(item.purchase)) * price)
        direct += subtotal
        lines.append(BudgetLine(item.key, item.description, item.unit, item.purchase, float(price), float(subtotal)))
    overhead, profit = _pct(direct, overhead_pct), _pct(direct, profit_pct)
    subtotal = direct + overhead + profit
    igv = _pct(subtotal, igv_pct)
    return Budget(
        lines=lines,
        direct_cost=float(direct),
        overhead_pct=overhead_pct,
        overhead=float(overhead),
        profit_pct=profit_pct,
        profit=float(profit),
        subtotal=float(subtotal),
        igv_pct=igv_pct,
        igv=float(igv),
        total=float(subtotal + igv),
        missing_prices=[i.key for i in items if i.key not in prices],
    )
