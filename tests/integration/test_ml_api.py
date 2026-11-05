"""Pruebas de integración: endpoints de ML con base de datos y modelos entrenados."""

import pytest

from tests.helpers import RECTANGULO_5x4, simulate_walk


@pytest.mark.evidencia(
    id="BI-26",
    nombre="GET /ml/info muestra los modelos cargados",
    requisito="RF-15",
    objetivo="Verificar que la API carga los .joblib y expone sus métricas de prueba.",
    entrada="Modelos en ml/modelos",
    esperado="HTTP 200 con modelo elegido y métricas de prueba de M1 y M2",
)
async def test_ml_info(client, api, evidencia):
    resp = await client.get(f"{api}/ml/info")
    body = resp.json()
    evidencia["obtenido"] = (
        f"HTTP {resp.status_code}, M1={body['corrector_muros']['modelo_elegido']}, "
        f"M2={body['clasificador_recorrido']['modelo_elegido']} (F1={body['clasificador_recorrido']['prueba']['f1']:.3f})"
    )
    assert resp.status_code == 200
    assert body["corrector_muros"]["tarea"] == "regresión"
    assert body["clasificador_recorrido"]["tarea"] == "clasificación"


@pytest.mark.evidencia(
    id="BI-27",
    nombre="Análisis ML de un recorrido guardado",
    requisito="RF-15",
    objetivo="Verificar la integración recorrido en BD → variables → modelos → respuesta.",
    entrada="Recorrido interior del aula 5×4 m con metadatos de captura (ARCore, 20 s)",
    esperado="HTTP 200, 4 muros corregidos y probabilidad de confiabilidad entre 0 y 1",
)
async def test_ml_recorrido(auth_client, project, api, evidencia):
    s = (
        await auth_client.post(
            f"{api}/projects/{project['id']}/surveys",
            json={"name": "Aula", "points": simulate_walk(RECTANGULO_5x4),
                  "capture": {"odometry": "arcore", "tracking_loss_s": 0, "duration_s": 20}},
        )
    ).json()
    resp = await auth_client.get(f"{api}/surveys/{s['id']}/ml")
    body = resp.json()
    evidencia["obtenido"] = (
        f"HTTP {resp.status_code}, P(confiable)={body['reliability_probability']:.3f}, "
        f"muros={[(round(w['measured_m'], 2), round(w['corrected_m'], 2)) for w in body['walls']]}"
    )
    assert resp.status_code == 200
    assert len(body["walls"]) == 4
    assert 0 <= body["reliability_probability"] <= 1


@pytest.mark.evidencia(
    id="BI-29",
    nombre="Recorrido del modo demostración de la app",
    requisito="RF-15, RF-17",
    objetivo="Verificar que el backend acepta el recorrido que envía la app en modo demo (capture.odometry='demo').",
    entrada="POST /projects/{id}/surveys con capture={odometry:'demo', tracking_loss_s:0, duration_s:18.5}",
    esperado="HTTP 201 y análisis ML disponible (HTTP 200)",
)
async def test_recorrido_modo_demo(auth_client, project, api, evidencia):
    s = await auth_client.post(
        f"{api}/projects/{project['id']}/surveys",
        json={"name": "Aula demo", "points": simulate_walk(RECTANGULO_5x4),
              "capture": {"odometry": "demo", "tracking_loss_s": 0, "duration_s": 18.5}},
    )
    ml = await auth_client.get(f"{api}/surveys/{s.json()['id']}/ml")
    evidencia["obtenido"] = f"crear HTTP {s.status_code}, ML HTTP {ml.status_code}"
    assert s.status_code == 201
    assert ml.status_code == 200


@pytest.mark.evidencia(
    id="BI-28",
    nombre="ML no aplica a recorridos exteriores",
    requisito="RF-15",
    objetivo="Verificar que los modelos (entrenados para interiores) no se aplican al modo GPS.",
    entrada="Recorrido en modo importado",
    esperado="HTTP 409",
)
async def test_ml_no_aplica(auth_client, project, api, evidencia):
    s = (
        await auth_client.post(
            f"{api}/projects/{project['id']}/surveys", json={"name": "Plano", "mode": "imported", "corners": RECTANGULO_5x4}
        )
    ).json()
    resp = await auth_client.get(f"{api}/surveys/{s['id']}/ml")
    evidencia["obtenido"] = f"HTTP {resp.status_code}: {resp.json()['detail']}"
    assert resp.status_code == 409
