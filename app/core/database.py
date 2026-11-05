"""Motor y sesiones de SQLAlchemy (async)."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    """Clase base de todos los modelos ORM."""


def engine_options(url: str) -> dict:
    """Opciones del motor. Con un pooler en modo transacción (PgBouncer, p. ej. Neon "-pooler")
    las sentencias preparadas en caché fallan ("prepared statement does not exist"): se desactivan."""
    if url.startswith("postgresql+asyncpg://") and "pooler" in url.split("@")[-1].split("/")[0]:
        return {"connect_args": {"statement_cache_size": 0, "prepared_statement_cache_size": 0}}
    return {}


engine = create_async_engine(settings.database_url, pool_pre_ping=True, **engine_options(settings.database_url))
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
