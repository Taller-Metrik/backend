"""Metrado de acabados de un ambiente con presupuesto (CU-07, RF-22 a RF-24)."""

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, status

from app.core.deps import CurrentUserDep, DbDep
from app.models.survey import SurveyMode
from app.schemas.finishes import FinishesIn, FinishesOut
from app.services.budget import build_budget
from app.services.finishes import FinishParams, Opening, finishes_takeoff
from app.services.geometry import GeometryError
from app.services.price_service import PriceService
from app.services.project_service import NotFoundError, SurveyService

router = APIRouter(tags=["Metrado de acabados"])


@router.post("/surveys/{survey_id}/finishes", response_model=FinishesOut)
async def survey_finishes(survey_id: int, payload: FinishesIn, db: DbDep, user: CurrentUserDep) -> FinishesOut:
    """Partidas e insumos para revestir el ambiente; presupuesto con precios del catálogo y de mano de obra."""
    try:
        survey = await SurveyService(db, user).get(survey_id)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recurso no encontrado") from None
    if survey.mode == SurveyMode.EXTERIOR:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El metrado de acabados aplica a ambientes interiores; para terrenos use el cerco perimétrico",
        )
    try:
        takeoff = finishes_takeoff(
            survey.area_m2,
            [float(w) for w in survey.wall_lengths_m],
            FinishParams(height_m=payload.height_m),
            [Opening(o.wall, o.kind, o.width_m, o.height_m) for o in payload.openings],
        )
    except GeometryError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from None

    item_keys = {i.key for i in takeoff.items}
    prices: dict[str, float] = {}
    sources: dict[str, str] = {}
    if payload.use_catalog:
        for p in await PriceService(db, user).list():
            if p.key in item_keys and p.price is not None:
                prices[p.key], sources[p.key] = p.price, p.source
    for key, price in (payload.labor_prices or {}).items():
        prices[key], sources[key] = price, "input"
    budget = (
        build_budget(takeoff.items, prices, overhead_pct=payload.overhead_pct, profit_pct=payload.profit_pct)
        if prices
        else None
    )
    return FinishesOut(
        survey_id=survey_id,
        area_m2=survey.area_m2,
        perimeter_m=survey.perimeter_m,
        height_m=payload.height_m,
        items=[asdict(i) for i in takeoff.items],
        assumptions=takeoff.assumptions,
        notes=takeoff.notes,
        budget=asdict(budget) if budget else None,
        price_sources=sources,
    )
