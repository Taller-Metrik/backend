"""Pruebas de integración: plano de vivienda con varios ambientes (CU-08, RF-25, RF-26)."""

import pytest


async def _ambiente(auth_client, api, project_id: int, name: str, corners) -> int:
    resp = await auth_client.post(
        f"{api}/projects/{project_id}/surveys", json={"name": name, "mode": "interior", "corners": corners}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.mark.evidencia(
    id="BI-50",
    nombre="Plano de vivienda y su DXF por la API",
    requisito="RF-25 / RF-26",
    objetivo="Verificar que la API une dos ambientes del proyecto, entrega el cuadro de áreas y el DXF de la planta completa.",
    precondiciones="Usuario autenticado con un proyecto y dos ambientes medidos",
    entrada="Sala 4×3 y Cocina 3×3 unidas por el muro este de la sala (espesor 0,15 m)",
    esperado="HTTP 200 con 2 ambientes y área total 21 m²; el DXF trae los dos nombres",
)
async def test_plano_vivienda(auth_client, project, api, evidencia):
    sala = await _ambiente(auth_client, api, project["id"], "Sala", [[0, 0], [4, 0], [4, 3], [0, 3]])
    cocina = await _ambiente(auth_client, api, project["id"], "Cocina", [[0, 0], [3, 0], [3, 3], [0, 3]])
    body = {
        "rooms": [sala, cocina],
        "joins": [{"a_survey": sala, "a_wall": 1, "b_survey": cocina, "b_wall": 3, "thickness_m": 0.15}],
    }
    resp = await auth_client.post(f"{api}/projects/{project['id']}/floor-plan", json=body)
    dxf = await auth_client.post(f"{api}/projects/{project['id']}/floor-plan.dxf", json=body)
    data = resp.json()
    evidencia["obtenido"] = (
        f"HTTP {resp.status_code}, ambientes={len(data['rooms'])}, área={data['total_area_m2']}, "
        f"DXF HTTP {dxf.status_code} ({len(dxf.content)} bytes)"
    )
    assert resp.status_code == 200
    assert len(data["rooms"]) == 2 and data["total_area_m2"] == pytest.approx(21.0)
    assert dxf.status_code == 200 and b"Sala" in dxf.content and b"Cocina" in dxf.content


@pytest.mark.evidencia(
    id="BI-51",
    nombre="Plano de vivienda con ambientes ajenos",
    requisito="RF-25 / RNF-07",
    objetivo="Verificar que solo se pueden unir ambientes del propio proyecto y que el proyecto debe existir.",
    entrada="Ambiente 9999 en la lista; proyecto 9999",
    esperado="HTTP 422 y 404",
)
async def test_plano_vivienda_errores(auth_client, project, api, evidencia):
    sala = await _ambiente(auth_client, api, project["id"], "Sala", [[0, 0], [4, 0], [4, 3], [0, 3]])
    r1 = await auth_client.post(f"{api}/projects/{project['id']}/floor-plan", json={"rooms": [sala, 9999], "joins": []})
    r2 = await auth_client.post(f"{api}/projects/9999/floor-plan", json={"rooms": [sala], "joins": []})
    evidencia["obtenido"] = f"{r1.status_code}, {r2.status_code}"
    assert (r1.status_code, r2.status_code) == (422, 404)
