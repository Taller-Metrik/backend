"""Punto de entrada de la API MetriK.

Ejecutar:  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
Docs:      http://localhost:8000/docs
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.models  # noqa: F401  (registra los modelos en Base.metadata)
from app.core.config import settings
from app.core.database import Base, engine
from app.routes import auth, field, floor_plan, geometry, gps, ml, projects, validation


@asynccontextmanager
async def lifespan(_: FastAPI):
    # En desarrollo se crean las tablas al iniciar. En producción usar Alembic.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


def create_app(*, use_lifespan: bool = True) -> FastAPI:
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Odómetro digital: genera planos de planta a escala a partir del recorrido del celular.",
        lifespan=lifespan if use_lifespan else None,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.get("/health", tags=["Sistema"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": settings.app_version}

    for router in (
        auth.router, geometry.router, gps.router, projects.router, validation.router, ml.router, field.router,
        floor_plan.router,
    ):
        application.include_router(router, prefix=settings.api_prefix)
    return application


app = create_app()
