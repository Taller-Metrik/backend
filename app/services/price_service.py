"""Precios efectivos para un usuario: el suyo si lo escribió; si no, el de la tienda (RF-23)."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.price import MaterialPrice, UserPrice
from app.models.user import User
from app.services.price_catalog import CATALOG, CATALOG_BY_KEY, STORE
from app.services.project_service import NotFoundError


@dataclass(frozen=True)
class PriceView:
    key: str
    description: str
    unit: str
    content: float
    content_unit: str
    price: float | None  # el que se usa: del usuario, si no de la tienda
    source: str  # user | store | none
    store_price: float | None
    store: str | None
    product_name: str | None
    url: str | None
    fetched_at: datetime | None
    status: str | None  # ok | error (último intento de la tienda)


class PriceService:
    def __init__(self, db: AsyncSession, user: User) -> None:
        self.db = db
        self.user = user

    async def list(self) -> list[PriceView]:
        store = {p.key: p for p in (await self.db.execute(select(MaterialPrice))).scalars()}
        own = {
            p.key: p.price
            for p in (await self.db.execute(select(UserPrice).where(UserPrice.user_id == self.user.id))).scalars()
        }
        views = []
        for c in CATALOG:
            s = store.get(c.key)
            store_price = s.price if s else None
            if c.key in own:
                price, source = own[c.key], "user"
            elif store_price is not None:
                price, source = store_price, "store"
            else:
                price, source = None, "none"
            views.append(PriceView(
                c.key, c.description, c.unit, c.content, c.content_unit, price, source, store_price,
                STORE if c.slug else None, s.product_name if s else None, s.url if s else None,
                s.fetched_at if s else None, s.status if s else None,
            ))
        return views

    async def set_own(self, key: str, price: float) -> PriceView:
        if key not in CATALOG_BY_KEY:
            raise NotFoundError
        row = (
            await self.db.execute(select(UserPrice).where(UserPrice.user_id == self.user.id, UserPrice.key == key))
        ).scalar_one_or_none()
        if row is None:
            self.db.add(UserPrice(user_id=self.user.id, key=key, price=price))
        else:
            row.price = price
        await self.db.commit()
        return next(v for v in await self.list() if v.key == key)

    async def delete_own(self, key: str) -> None:
        if key not in CATALOG_BY_KEY:
            raise NotFoundError
        await self.db.execute(delete(UserPrice).where(UserPrice.user_id == self.user.id, UserPrice.key == key))
        await self.db.commit()
