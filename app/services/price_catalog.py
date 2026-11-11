"""Catálogo de precios de materiales por scraping de tienda (RF-23).

- Fuente: catálogo público VTEX de Promart (`/api/catalog_system/pub/products/search/<slug>/p`), permitido
  por su robots.txt. Sodimac se descartó porque su robots.txt prohíbe las páginas de producto.
- Se consulta un producto fijo por material (más estable que una búsqueda libre), una vez al día, con una
  pausa entre consultas. Si la tienda falla se conserva el último precio válido (EX-09).
- La consulta HTTP se inyecta (`fetch`): el job usa Scrapling (`price_scraper.fetch_json`) y las pruebas una
  tienda simulada, así el API no depende de Scrapling ni de internet.
"""

import asyncio
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.price import MaterialPrice

STORE = "Promart"
MAX_PRICE = 1_000_000.0  # tope de cordura (la columna admite hasta 99 999 999,99)
STORE_API = "https://www.promart.pe/api/catalog_system/pub/products/search/{slug}/p"


@dataclass(frozen=True)
class CatalogEntry:
    key: str
    description: str
    unit: str  # unidad de venta
    content: float  # contenido de la unidad de venta
    content_unit: str
    slug: str | None  # producto en la tienda; None = sin producto (solo precio del usuario)


CATALOG: tuple[CatalogEntry, ...] = (
    CatalogEntry("cement_bag", "Cemento Portland tipo I", "bolsa", 42.5, "kg", "cemento-portland-tipo-i-x42-5kg-sol"),
    CatalogEntry("sand_bag", "Arena gruesa", "saco", 40.0, "kg", "arena-gruesa-unicon-40kg"),
    CatalogEntry("stone_bag", "Piedra chancada", "saco", 40.0, "kg", "piedra-chancada-unicon-40kg"),
    CatalogEntry("paint_gallon", "Pintura látex", "galón", 1.0, "gal", "duralatex-cpp-blanco-1-galon"),
    CatalogEntry("porcelain_box", "Porcelanato 60 × 60 cm", "caja", 1.44, "m²",
                 "piso-porcelanato-liso-unicolor-gris-60x60cm-1-44m2-167830"),
    CatalogEntry("brick_kk18", "Ladrillo King Kong 18 huecos", "und", 1.0, "und", "ladrillo-king-kong-18-huecos"),
    CatalogEntry("barbed_wire_roll", "Alambre de púas", "rollo", 200.0, "m", "alambre-puas-motto-x-200-m"),
    CatalogEntry("rebar_3_8", "Fierro corrugado 3/8\"", "barra", 9.0, "m", "barra-de-construccion-a615-astm-3-8x9-metros"),
    CatalogEntry("fine_sand_bag", "Arena fina (tarrajeo)", "saco", 40.0, "kg", "arena-fina-unicon-40kg"),
    CatalogEntry("primer_4gal", "Imprimante", "balde", 4.0, "gal", "imprimante-blanco-4-galones"),
    CatalogEntry("grout_kg", "Fragua para porcelanato", "bolsa", 1.0, "kg", "fragua-super-porcelana-crema-1kg"),
    CatalogEntry("pine_post", "Madera pino 1\" × 2\" × 3,2 m (postes y pies de amigo)", "und", 1.0, "und",
                 "madera-pino-radiata-1-x2-x10-5--gc"),
    CatalogEntry("staples_bag", "Grapas Motto 1\" × 9 para cerco", "bolsa", 0.5, "kg", "grapa-motto-1--x-9---1-2-kg"),
    CatalogEntry("tile_adhesive_bag", "Pegamento para porcelanato", "bolsa", 25.0, "kg", None),
)
CATALOG_BY_KEY = {c.key: c for c in CATALOG}


class PriceParseError(ValueError):
    """La respuesta de la tienda no trae un producto con precio válido."""


@dataclass(frozen=True)
class ScrapedPrice:
    product_name: str
    price: float
    available: bool
    url: str


def product_url(slug: str) -> str:
    return STORE_API.format(slug=slug)


def parse_vtex_product(data: Any) -> ScrapedPrice:
    """Extrae nombre, precio, disponibilidad y enlace de la respuesta del catálogo VTEX."""
    if not isinstance(data, list) or not data:
        raise PriceParseError("La tienda no devolvió el producto")
    try:
        product = data[0]
        offer = product["items"][0]["sellers"][0]["commertialOffer"]
        price = float(offer["Price"])
        name = str(product["productName"])[:200]  # tamaño de la columna
        url = str(product.get("link") or "")
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise PriceParseError(f"Respuesta de la tienda con formato inesperado ({type(exc).__name__})") from exc
    if not math.isfinite(price) or not 0 < price < MAX_PRICE:
        raise PriceParseError("El producto no tiene un precio publicado válido")
    # Solo se guardan enlaces seguros y que entren en la columna
    safe_url = url if url.startswith("https://") and len(url) <= 300 else ""
    return ScrapedPrice(name, round(price, 2), int(offer.get("AvailableQuantity") or 0) > 0, safe_url)


@dataclass
class RefreshReport:
    updated: int = 0
    failed: int = 0
    errors: dict[str, str] = field(default_factory=dict)


async def refresh_prices(
    db: AsyncSession,
    fetch: Callable[[str], Any],
    *,
    delay_s: float = 2.0,
) -> RefreshReport:
    """Actualiza el precio de cada material con producto en la tienda. `fetch(url)` devuelve el JSON.

    Cada material se guarda en su propia transacción: un fallo (de la tienda o de la base de datos) no hace
    perder las actualizaciones de los demás.
    """
    report = RefreshReport()
    for i, entry in enumerate(c for c in CATALOG if c.slug):
        if i and delay_s:
            await asyncio.sleep(delay_s)  # una consulta cada pocos segundos: tráfico mínimo para la tienda
        try:
            scraped: ScrapedPrice | Exception = parse_vtex_product(
                await asyncio.to_thread(fetch, product_url(entry.slug))  # type: ignore[arg-type]
            )
        except Exception as exc:  # noqa: BLE001 - cualquier fallo de la tienda se registra y se sigue
            scraped = exc
        try:
            await _save(db, entry.key, scraped)
        except Exception as exc:  # noqa: BLE001 - un fallo al guardar no detiene a los demás materiales
            await db.rollback()
            scraped = exc
        if isinstance(scraped, Exception):
            report.failed += 1
            report.errors[entry.key] = f"{type(scraped).__name__}: {scraped}"[:200]
        else:
            report.updated += 1
    return report


async def _save(db: AsyncSession, key: str, scraped: "ScrapedPrice | Exception") -> None:
    now = datetime.now(UTC)
    row = await db.get(MaterialPrice, key)
    if row is None:
        row = MaterialPrice(key=key, store=STORE)
        db.add(row)
    row.checked_at = now
    if isinstance(scraped, Exception):
        row.status, row.error = "error", f"{type(scraped).__name__}: {scraped}"[:200]  # se conserva el último precio
    else:
        row.product_name, row.url, row.price = scraped.product_name, scraped.url or None, scraped.price
        row.available, row.fetched_at, row.status, row.error = scraped.available, now, "ok", None
    await db.commit()
