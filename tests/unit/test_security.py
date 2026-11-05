"""Pruebas unitarias de seguridad: hash de contraseñas y tokens JWT."""

import time

import pytest

from app.core.security import (
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


@pytest.mark.evidencia(
    id="BU-01",
    nombre="Hash y verificación de contraseña correcta",
    requisito="RNF-07",
    objetivo="Verificar que la contraseña se guarda con hash bcrypt y se valida correctamente.",
    entrada="Contraseña 'clave-segura-123'",
    esperado="El hash es distinto al texto plano, empieza con '$2b$' y verify_password devuelve True",
)
def test_hash_y_verificacion_correcta(evidencia):
    hashed = hash_password("clave-segura-123")
    ok = verify_password("clave-segura-123", hashed)
    evidencia["obtenido"] = f"hash={hashed[:7]}... verificado={ok}"
    assert hashed != "clave-segura-123"
    assert hashed.startswith("$2b$")
    assert ok is True


@pytest.mark.evidencia(
    id="BU-02",
    nombre="Rechazo de contraseña incorrecta",
    requisito="RNF-07",
    objetivo="Verificar que una contraseña distinta no se valida contra el hash.",
    entrada="Hash de 'clave-segura-123', intento con 'otra-clave'",
    esperado="verify_password devuelve False",
)
def test_contrasena_incorrecta(evidencia):
    hashed = hash_password("clave-segura-123")
    ok = verify_password("otra-clave", hashed)
    evidencia["obtenido"] = f"verificado={ok}"
    assert ok is False


@pytest.mark.evidencia(
    id="BU-03",
    nombre="Generación y lectura de token JWT",
    requisito="RF-16",
    objetivo="Verificar que el token JWT conserva el id del usuario.",
    entrada="Usuario con id 42",
    esperado="decode_access_token devuelve '42'",
)
def test_token_ida_y_vuelta(evidencia):
    token = create_access_token(42)
    sujeto = decode_access_token(token)
    evidencia["obtenido"] = f"sujeto='{sujeto}'"
    assert sujeto == "42"


@pytest.mark.evidencia(
    id="BU-04",
    nombre="Rechazo de token expirado",
    requisito="RNF-07",
    objetivo="Verificar que un token vencido no es aceptado.",
    entrada="Token con expiración de -1 minuto",
    esperado="Se lanza InvalidTokenError",
)
def test_token_expirado(evidencia):
    token = create_access_token(1, expires_minutes=-1)
    time.sleep(0.01)
    with pytest.raises(InvalidTokenError) as exc:
        decode_access_token(token)
    evidencia["obtenido"] = f"InvalidTokenError: {exc.value}"


@pytest.mark.evidencia(
    id="BU-05",
    nombre="Rechazo de token alterado",
    requisito="RNF-07",
    objetivo="Verificar que un token modificado (firma inválida) es rechazado.",
    entrada="Token válido con el último carácter cambiado",
    esperado="Se lanza InvalidTokenError",
)
def test_token_alterado(evidencia):
    token = create_access_token(1)
    alterado = token[:-1] + ("A" if token[-1] != "A" else "B")
    with pytest.raises(InvalidTokenError) as exc:
        decode_access_token(alterado)
    evidencia["obtenido"] = f"InvalidTokenError: {exc.value}"
