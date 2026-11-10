"""Consulta HTTP a la tienda con Scrapling, solo para el job diario de precios (RF-23).

Se usa el `Fetcher` HTTP simple (sin navegador ni modo stealth): la API de catálogo de Promart es pública y
su robots.txt la permite. Scrapling se instala aparte (`requirements-scraper.txt`); el API no lo necesita.
"""

import json
from typing import Any


def fetch_json(url: str) -> Any:
    from scrapling.fetchers import Fetcher  # importación diferida: solo existe en el entorno del job

    response = Fetcher.get(url, timeout=20)
    if response.status >= 400:
        raise ConnectionError(f"HTTP {response.status}")
    return json.loads(response.body)
