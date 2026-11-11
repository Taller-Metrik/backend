"""Job diario: actualiza el catálogo de precios desde la tienda (RF-23).

Uso (con DATABASE_URL apuntando a la base de datos):

    pip install -r requirements.txt -r requirements-scraper.txt
    python -m scripts.actualizar_precios

Códigos de salida: 0 = todos los materiales actualizados; 1 = falló alguno (los demás sí se guardaron;
el error queda en el registro de cada material); 2 = error inesperado (por ejemplo, sin base de datos).
"""

import asyncio
import sys

from app.core.database import SessionLocal
from app.services.price_catalog import refresh_prices
from app.services.price_scraper import fetch_json


async def main() -> int:
    try:
        async with SessionLocal() as db:
            report = await refresh_prices(db, fetch_json)
    except Exception as exc:  # noqa: BLE001 - se informa y se sale con código de error
        print(f"::error::No se pudo actualizar el catálogo: {type(exc).__name__}: {exc}")
        return 2
    print(f"Precios actualizados: {report.updated}; con error: {report.failed}")
    for key, error in report.errors.items():
        print(f"::warning::{key}: {error}")  # aviso visible en GitHub Actions
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
