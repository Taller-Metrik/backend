"""Pruebas de integración: proyectos y recorridos con base de datos."""

import pytest
from sqlalchemy import func, select

from app.models.survey import Survey
from tests.helpers import RECTANGULO_5x4, simulate_walk


@pytest.mark.evidencia(
    id="BI-11",
    nombre="Crear y listar proyectos del usuario",
    requisito="RF-16",
    objetivo="Verificar que un usuario autenticado crea proyectos y solo ve los suyos.",
    entrada="Usuario A crea 2 proyectos; usuario B crea 1",
    esperado="A lista 2 proyectos; B lista 1",
)
async def test_crear_y_listar_proyectos(auth_client, client, api, evidencia):
    await auth_client.post(f"{api}/projects", json={"name": "Casa"})
    await auth_client.post(f"{api}/projects", json={"name": "Oficina"})
    lista_a = (await auth_client.get(f"{api}/projects")).json()

    otro = {"email": "beto@metrik.pe", "full_name": "Beto", "password": "clave-de-beto-1"}
    await client.post(f"{api}/auth/register", json=otro)
    token = (await client.post(f"{api}/auth/login", data={"username": otro["email"], "password": otro["password"]})).json()
    headers_b = {"Authorization": f"Bearer {token['access_token']}"}
    await client.post(f"{api}/projects", json={"name": "Terreno"}, headers=headers_b)
    lista_b = (await client.get(f"{api}/projects", headers=headers_b)).json()

    evidencia["obtenido"] = f"A={[p['name'] for p in lista_a]}, B={[p['name'] for p in lista_b]}"
    assert {p["name"] for p in lista_a} == {"Casa", "Oficina"}
    assert [p["name"] for p in lista_b] == ["Terreno"]


@pytest.mark.evidencia(
    id="BI-12",
    nombre="Aislamiento de proyectos entre usuarios",
    requisito="RNF-07",
    objetivo="Verificar que un usuario no puede ver ni borrar el proyecto de otro.",
    entrada="Usuario B intenta GET y DELETE sobre el proyecto de A",
    esperado="HTTP 404 en ambos casos y el proyecto sigue existiendo",
)
async def test_aislamiento_entre_usuarios(auth_client, client, project, api, evidencia):
    otro = {"email": "intruso@metrik.pe", "full_name": "Intruso", "password": "clave-intruso-1"}
    await client.post(f"{api}/auth/register", json=otro)
    token = (await client.post(f"{api}/auth/login", data={"username": otro["email"], "password": otro["password"]})).json()
    headers_b = {"Authorization": f"Bearer {token['access_token']}"}

    r_get = await client.get(f"{api}/projects/{project['id']}", headers=headers_b)
    r_del = await client.delete(f"{api}/projects/{project['id']}", headers=headers_b)
    sigue = await auth_client.get(f"{api}/projects/{project['id']}")
    evidencia["obtenido"] = f"GET={r_get.status_code}, DELETE={r_del.status_code}, dueño ve={sigue.status_code}"
    assert (r_get.status_code, r_del.status_code, sigue.status_code) == (404, 404, 200)


@pytest.mark.evidencia(
    id="BI-13",
    nombre="Crear recorrido interior y persistir el plano",
    requisito="RF-01, RF-05, RF-17",
    objetivo="Verificar que POST /projects/{id}/surveys procesa y guarda el plano en BD.",
    entrada="Trazo simulado de aula 5×4 m (≈ 360 puntos)",
    esperado="HTTP 201, registro en BD con 4 vértices y área ≈ 20 m²",
)
async def test_crear_recorrido(auth_client, project, db_session, api, evidencia):
    resp = await auth_client.post(
        f"{api}/projects/{project['id']}/surveys",
        json={"name": "Aula 201", "points": simulate_walk(RECTANGULO_5x4), "device_model": "Samsung Galaxy A25"},
    )
    body = resp.json()
    guardado = await db_session.get(Survey, body["id"])
    evidencia["obtenido"] = (
        f"HTTP {resp.status_code}, BD: vértices={len(guardado.vertices)}, área={guardado.area_m2:.3f}, "
        f"puntos crudos={len(guardado.raw_points)}"
    )
    assert resp.status_code == 201
    assert len(guardado.vertices) == 4
    assert guardado.area_m2 == pytest.approx(20.0, rel=0.02)


@pytest.mark.evidencia(
    id="BI-14",
    nombre="Borrar proyecto elimina sus recorridos (cascada)",
    requisito="RF-16",
    objetivo="Verificar la integridad referencial entre proyectos y recorridos.",
    entrada="Proyecto con 2 recorridos → DELETE /projects/{id}",
    esperado="HTTP 204 y 0 recorridos en BD",
)
async def test_borrado_en_cascada(auth_client, project, db_session, api, evidencia):
    for nombre in ("A", "B"):
        await auth_client.post(
            f"{api}/projects/{project['id']}/surveys", json={"name": nombre, "corners": RECTANGULO_5x4 + [(0, 0)]}
        )
    resp = await auth_client.delete(f"{api}/projects/{project['id']}")
    restantes = (await db_session.execute(select(func.count(Survey.id)))).scalar_one()
    evidencia["obtenido"] = f"HTTP {resp.status_code}, recorridos restantes={restantes}"
    assert resp.status_code == 204
    assert restantes == 0


@pytest.mark.evidencia(
    id="BI-15",
    nombre="Recorrido en proyecto inexistente",
    requisito="RF-16",
    objetivo="Verificar la respuesta ante un proyecto que no existe.",
    entrada="POST /projects/9999/surveys",
    esperado="HTTP 404",
)
async def test_recorrido_proyecto_inexistente(auth_client, api, evidencia):
    resp = await auth_client.post(f"{api}/projects/9999/surveys", json={"name": "X", "corners": RECTANGULO_5x4})
    evidencia["obtenido"] = f"HTTP {resp.status_code}"
    assert resp.status_code == 404
