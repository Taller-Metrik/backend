"""Catálogo de precios de materiales (RF-23)."""

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Path, Response, status

from app.core.deps import CurrentUserDep, DbDep
from app.schemas.prices import PriceIn, PriceOut
from app.services.price_service import PriceService
from app.services.project_service import NotFoundError

router = APIRouter(prefix="/prices", tags=["Catálogo de precios"])

def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material no encontrado en el catálogo")


KeyPath = Path(min_length=1, max_length=40)


@router.get("", response_model=list[PriceOut])
async def list_prices(db: DbDep, user: CurrentUserDep) -> list[PriceOut]:
    """Precio de cada material: el del usuario si lo escribió; si no, el de la tienda con su fecha."""
    return [PriceOut(**asdict(v)) for v in await PriceService(db, user).list()]


@router.put("/{key}", response_model=PriceOut)
async def set_own_price(payload: PriceIn, db: DbDep, user: CurrentUserDep, key: str = KeyPath) -> PriceOut:
    """Guarda el precio propio del usuario para un material."""
    try:
        return PriceOut(**asdict(await PriceService(db, user).set_own(key, payload.price)))
    except NotFoundError:
        raise _not_found() from None


@router.delete("/{key}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_own_price(db: DbDep, user: CurrentUserDep, key: str = KeyPath) -> Response:
    """Vuelve a usar el precio de la tienda."""
    try:
        await PriceService(db, user).delete_own(key)
    except NotFoundError:
        raise _not_found() from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
