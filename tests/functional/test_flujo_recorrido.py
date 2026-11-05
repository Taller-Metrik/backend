"""Pruebas funcionales: caso de uso de levantamiento interior completo (CU-01)."""

import pytest

from tests.helpers import AMBIENTE_U, simulate_walk


@pytest.mark.evidencia(
    id="BF-04",
    nombre="Levantar el plano de un ambiente y consultarlo",
    requisito="CU-01 (RF-01, RF-05, RF-06, RF-10, RF-16)",
    objetivo="Verificar el caso de uso completo de levantamiento interior a través de la API.",
    precondiciones="Usuario nuevo, sin proyectos",
    entrada="Registro → login → crear proyecto → subir recorrido de ambiente en U → listar → ver detalle",
    esperado="Plano de 8 muros con 2 vértices cóncavos, área 24 m² ± 2 %, visible en el listado del proyecto",
)
async def test_levantamiento_interior(client, api, evidencia):
    usuario = {"email": "topo@metrik.pe", "full_name": "Topógrafa", "password": "clave-topo-2026"}
    await client.post(f"{api}/auth/register", json=usuario)
    token = (await client.post(f"{api}/auth/login", data={"username": usuario["email"], "password": usuario["password"]})).json()
    client.headers["Authorization"] = f"Bearer {token['access_token']}"

    proyecto = (await client.post(f"{api}/projects", json={"name": "Laboratorio"})).json()
    creado = await client.post(
        f"{api}/projects/{proyecto['id']}/surveys",
        json={"name": "Lab de cómputo", "points": simulate_walk(AMBIENTE_U, seed=7)},
    )
    listado = (await client.get(f"{api}/projects/{proyecto['id']}/surveys")).json()
    detalle = (await client.get(f"{api}/surveys/{creado.json()['id']}")).json()

    evidencia["obtenido"] = (
        f"HTTP {creado.status_code}, listado={len(listado)}, muros={len(detalle['wall_lengths_m'])}, "
        f"cóncavos={detalle['concave_count']}, área={detalle['area_m2']:.3f} m², escala=1:{detalle['scale_denominator']}"
    )
    assert creado.status_code == 201
    assert len(listado) == 1 and listado[0]["name"] == "Lab de cómputo"
    assert len(detalle["wall_lengths_m"]) == 8 and detalle["concave_count"] == 2
    assert detalle["area_m2"] == pytest.approx(24.0, rel=0.02)
