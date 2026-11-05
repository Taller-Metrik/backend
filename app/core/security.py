"""Hash de contraseñas (bcrypt) y tokens JWT."""

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import settings


class InvalidTokenError(Exception):
    """El token es inválido, expiró o no tiene sujeto."""


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(subject: str | int, expires_minutes: int | None = None) -> str:
    minutes = expires_minutes if expires_minutes is not None else settings.access_token_expire_minutes
    now = datetime.now(UTC)
    payload = {"sub": str(subject), "iat": now, "exp": now + timedelta(minutes=minutes)}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> str:
    """Devuelve el sujeto (id de usuario) del token o lanza InvalidTokenError."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc
    subject = payload.get("sub")
    if not subject:
        raise InvalidTokenError("Token sin sujeto")
    return str(subject)
