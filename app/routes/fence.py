"""Cerco perimétrico: metrado con rango de compra y presupuesto (CU-09, RF-24, RF-27)."""

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, status

from app.core.deps import CurrentUserDep, DbDep
from app.schemas.fence import FenceIn, FenceOut
from app.services.budget import build_budget
from app.services.fence import FenceParams, Gate, fence_takeoff
from app.services.geometry import GeometryError
from app.services.fence_prices import CatalogPrice, unit_prices
from app.services.price_service import PriceService
from app.services.project_service import NotFoundError, SurveyService

router = APIRouter(tags=["Cerco perimétrico"])

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
        if payload.use_catalog:
            catalog = {
                p.key: CatalogPrice(float(p.price), p.source)
                for p in await PriceService(db, user).list()
                if p.price is not None
            }
            priceable = {i.key for i in takeoff.items if i.priceable}
            for key, (price, source) in unit_prices(priceable, catalog, params).items():
                prices[key], sources[key] = price, source
            if sources:
                takeoff.notes.append(
                    "Precios de la tienda: solo materiales (sin mano de obra); encofrado, excavación y portones "
                    "se presupuestan con el precio que escribas."
                )
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
