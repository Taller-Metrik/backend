"""Metrado de acabados de un ambiente con presupuesto (CU-07, RF-22 a RF-24)."""

from dataclasses import asdict
from datetime import UTC, datetime, timedelta

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
STALE_AFTER = timedelta(days=7)  # un precio de tienda más antiguo se usa, pero con aviso


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
            [float(w) for w in survey.wall_lengths_m or []],  # recorridos antiguos sin muros → 422, no 500
            FinishParams(height_m=payload.height_m),
            [Opening(o.wall, o.kind, o.width_m, o.height_m) for o in payload.openings],
        )
    except GeometryError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from None

    item_keys = {i.key for i in takeoff.items}
    prices: dict[str, float] = {}
    sources: dict[str, str] = {}
    warnings: list[str] = []
    now = datetime.now(UTC)
    if payload.use_catalog:
        for p in await PriceService(db, user).list():
            if p.key not in item_keys or p.price is None:
                continue
            prices[p.key], sources[p.key] = p.price, p.source
            if p.source == "store" and p.fetched_at and now - p.fetched_at > STALE_AFTER:
                warnings.append(f"El precio de «{p.description}» es del {p.fetched_at:%d/%m/%Y} (más de 7 días).")
            if p.source == "store" and p.status == "error":
                warnings.append(f"La última consulta a la tienda de «{p.description}» falló: se usa el último precio.")
    for key, price in (payload.labor_prices or {}).items():
        prices[key], sources[key] = price, "input"
    budget = (
        build_budget(takeoff.items, prices, overhead_pct=payload.overhead_pct, profit_pct=payload.profit_pct)
        if prices
        else None
    )
    if budget and budget.missing_prices:
        warnings.append(f"{len(budget.missing_prices)} partidas sin precio no entran al presupuesto: el total es parcial.")
    return FinishesOut(
        survey_id=survey_id,
        area_m2=survey.area_m2,
        perimeter_m=survey.perimeter_m,
        height_m=payload.height_m,
        items=[asdict(i) for i in takeoff.items],
        assumptions=takeoff.assumptions,
        notes=takeoff.notes + warnings,
        budget=asdict(budget) if budget else None,
        price_sources=sources,
    )
