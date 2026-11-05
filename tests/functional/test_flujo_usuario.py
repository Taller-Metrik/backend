"""Pruebas funcionales: caso de uso completo de cuenta de usuario (RF-16)."""

import pytest


@pytest.mark.evidencia(
    id="BF-01",
    nombre="Flujo de cuenta: registro, inicio de sesión y perfil",
    requisito="RF-16",
    objetivo="Verificar el caso de uso completo de un usuario nuevo a través de la API.",
    precondiciones="API en ejecución con base de datos vacía",
    entrada="Registro → login → GET /auth/me con el token",
    esperado="Registro 201, login 200, /me 200 con el mismo correo y nombre",
)
async def test_flujo_cuenta_completo(client, api, evidencia):
    nuevo = {"email": "Luis@MetriK.pe", "full_name": "Luis Topógrafo", "password": "otra-clave-456"}

    r1 = await client.post(f"{api}/auth/register", json=nuevo)
    r2 = await client.post(f"{api}/auth/login", data={"username": "luis@metrik.pe", "password": nuevo["password"]})
    token = r2.json()["access_token"]
    r3 = await client.get(f"{api}/auth/me", headers={"Authorization": f"Bearer {token}"})

    evidencia["obtenido"] = (
        f"registro={r1.status_code}, login={r2.status_code}, me={r3.status_code}, email={r3.json()['email']}"
    )
    assert (r1.status_code, r2.status_code, r3.status_code) == (201, 200, 200)
    assert r3.json()["email"] == "luis@metrik.pe"
    assert r3.json()["full_name"] == "Luis Topógrafo"
