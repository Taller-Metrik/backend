"""Pruebas de integración: endpoints de autenticación + base de datos."""

import pytest
from sqlalchemy import select

from app.models.user import User
from tests.conftest import USUARIO


@pytest.mark.evidencia(
    id="BI-01",
    nombre="Registro de usuario persiste en la base de datos",
    requisito="RF-16",
    objetivo="Verificar que POST /auth/register crea el usuario en BD con la contraseña hasheada.",
    entrada=f"email={USUARIO['email']}, full_name={USUARIO['full_name']}",
    esperado="HTTP 201, usuario en BD, hashed_password distinto de la contraseña",
)
async def test_registro_persiste(client, db_session, api, evidencia):
    resp = await client.post(f"{api}/auth/register", json=USUARIO)
    user = (await db_session.execute(select(User).where(User.email == USUARIO["email"]))).scalar_one()
    evidencia["obtenido"] = f"HTTP {resp.status_code}, id={user.id}, hash={user.hashed_password[:7]}..."
    assert resp.status_code == 201
    assert "password" not in resp.json() and "hashed_password" not in resp.json()
    assert user.hashed_password != USUARIO["password"]


@pytest.mark.evidencia(
    id="BI-02",
    nombre="Registro con correo duplicado",
    requisito="RF-16",
    objetivo="Verificar que no se puede registrar dos veces el mismo correo.",
    entrada="Dos registros con el mismo email",
    esperado="El segundo devuelve HTTP 409",
)
async def test_registro_duplicado(client, registered_user, api, evidencia):
    resp = await client.post(f"{api}/auth/register", json=USUARIO)
    evidencia["obtenido"] = f"HTTP {resp.status_code}: {resp.json()['detail']}"
    assert resp.status_code == 409


@pytest.mark.evidencia(
    id="BI-03",
    nombre="Inicio de sesión con credenciales válidas",
    requisito="RF-16",
    objetivo="Verificar que POST /auth/login devuelve un token JWT.",
    entrada="Usuario registrado con su contraseña correcta",
    esperado="HTTP 200 y access_token de tipo bearer",
)
async def test_login_valido(client, registered_user, api, evidencia):
    resp = await client.post(
        f"{api}/auth/login", data={"username": USUARIO["email"], "password": USUARIO["password"]}
    )
    body = resp.json()
    evidencia["obtenido"] = f"HTTP {resp.status_code}, token_type={body.get('token_type')}"
    assert resp.status_code == 200
    assert body["token_type"] == "bearer" and body["access_token"]


@pytest.mark.evidencia(
    id="BI-04",
    nombre="Inicio de sesión con contraseña incorrecta",
    requisito="RNF-07",
    objetivo="Verificar que una contraseña incorrecta no permite iniciar sesión.",
    entrada="Usuario registrado con contraseña 'incorrecta'",
    esperado="HTTP 401",
)
async def test_login_invalido(client, registered_user, api, evidencia):
    resp = await client.post(f"{api}/auth/login", data={"username": USUARIO["email"], "password": "incorrecta"})
    evidencia["obtenido"] = f"HTTP {resp.status_code}: {resp.json()['detail']}"
    assert resp.status_code == 401


@pytest.mark.evidencia(
    id="BI-05",
    nombre="Acceso a ruta protegida sin token",
    requisito="RNF-07",
    objetivo="Verificar que GET /auth/me exige autenticación.",
    entrada="Petición sin cabecera Authorization",
    esperado="HTTP 401",
)
async def test_me_sin_token(client, api, evidencia):
    resp = await client.get(f"{api}/auth/me")
    evidencia["obtenido"] = f"HTTP {resp.status_code}"
    assert resp.status_code == 401
