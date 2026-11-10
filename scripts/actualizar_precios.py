"""Job diario: actualiza el catálogo de precios desde la tienda (RF-23).

Uso (con DATABASE_URL apuntando a la base de datos):

    pip install -r requirements.txt -r requirements-scraper.txt
    python -m scripts.actualizar_precios

Termina con código 1 si ningún material se pudo actualizar (la tienda no responde o cambió su formato).
"""

import asyncio
import sys

from app.core.database import SessionLocal
from app.services.price_catalog import refresh_prices
from app.services.price_scraper import fetch_json


async def main() -> int:
    async with SessionLocal() as db:
        report = await refresh_prices(db, fetch_json)
    print(f"Precios actualizados: {report.updated}; con error: {report.failed}")
    for key, error in report.errors.items():
        print(f"  {key}: {error}")
    return 0 if report.updated else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
