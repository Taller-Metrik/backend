"""Cerco perimétrico: metrado con rango de compra y presupuesto (CU-09, RF-24, RF-27)."""

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, status

from app.core.deps import CurrentUserDep, DbDep
from app.schemas.fence import FenceIn, FenceOut
from app.services.budget import build_budget
from app.services.fence import FenceParams, Gate, fence_takeoff
from app.services.geometry import GeometryError
from app.services.price_catalog import CATALOG_BY_KEY
from app.services.price_service import PriceService
from app.services.project_service import NotFoundError, SurveyService

router = APIRouter(tags=["Cerco perimétrico"])

# Grapas 1" × 9 (BWG): unas 170 por kg
STAPLES_PER_KG = 170.0


def catalog_unit_price(item_key: str, catalog_price: dict[str, float], roll_m: float) -> tuple[float, str] | None:
    """Precio unitario de una partida del cerco de alambre a partir del catálogo y la clave usada (o None)."""
    if item_key in ("posts_total", "braces") and "pine_post" in catalog_price:
        return catalog_price["pine_post"], "pine_post"
    if item_key == "wire_rolls" and "barbed_wire_roll" in catalog_price:
        roll = CATALOG_BY_KEY["barbed_wire_roll"]
        return catalog_price["barbed_wire_roll"] * roll_m / roll.content, "barbed_wire_roll"
    if item_key == "staples" and "staples_bag" in catalog_price:
        bag = CATALOG_BY_KEY["staples_bag"]
        return catalog_price["staples_bag"] / (bag.content * STAPLES_PER_KG), "staples_bag"
    return None


@router.post("/surveys/{survey_id}/fence", response_model=FenceOut)
async def survey_fence(survey_id: int, payload: FenceIn, db: DbDep, user: CurrentUserDep) -> FenceOut:
    """Metrado del cerco sobre los lados del recorrido; con precios, también el presupuesto con IGV."""
    try:
        survey = await SurveyService(db, user).get(survey_id)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recurso no encontrado") from None
    params = FenceParams(
        kind=payload.kind,
        post_spacing_m=payload.post_spacing_m,
        strands=payload.strands,
        wall_height_m=payload.wall_height_m,
        column_spacing_m=payload.column_spacing_m,
    )
    u95 = (survey.uncertainty or {}).get("perimeter_u95_m")
    valid_u95 = isinstance(u95, int | float) and not isinstance(u95, bool)
    try:
        takeoff = fence_takeoff(
            [float(w) for w in survey.wall_lengths_m],
            params,
            gates=[Gate(g.side, g.width_m) for g in payload.gates],
            perimeter_u95_m=float(u95) if valid_u95 else None,
        )
        prices: dict[str, float] = {}
        sources: dict[str, str] = {}
        if payload.use_catalog and payload.kind == "wire":
            catalog = {p.key: p for p in await PriceService(db, user).list() if p.price is not None}
            catalog_price = {k: float(p.price) for k, p in catalog.items()}
            for item in takeoff.items:
                found = catalog_unit_price(item.key, catalog_price, params.roll_m) if item.priceable else None
                if found:
                    prices[item.key], sources[item.key] = round(found[0], 4), catalog[found[1]].source
        for key, price in (payload.prices or {}).items():
            prices[key], sources[key] = price, "input"
        budget = (
            build_budget(takeoff.items, prices, overhead_pct=payload.overhead_pct, profit_pct=payload.profit_pct)
            if prices or payload.prices is not None
            else None
        )
    except GeometryError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from None
    return FenceOut(
        survey_id=survey_id, **asdict(takeoff), budget=asdict(budget) if budget else None, price_sources=sources,
    )
