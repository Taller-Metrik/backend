"""Pruebas de integración: precisión GPS (esquinas fijadas, señal e incertidumbre) por la API."""

import pytest

from tests.helpers import TERRENO_100x60, simulate_gps_walk, simulate_stop_and_go


@pytest.mark.evidencia(
    id="BI-34",
    nombre="POST /gps/area con esquinas fijadas devuelve la incertidumbre",
    requisito="RF-18 / RF-21",
    objetivo="Verificar que la API usa las esquinas fijadas e informa el área con su incertidumbre al 95 %.",
    entrada="Recorrido stop-and-go del terreno 100×60 m (60 s por esquina) con 8 satélites y 35 dB-Hz",
    esperado="HTTP 200, método stop_and_go, área 6000 ± 3 % y dentro de ± U95 (U95 < 10 %), cierre informado",
)
async def test_gps_area_stop_and_go(client, api, evidencia):
    puntos = simulate_stop_and_go(TERRENO_100x60, satellites=8, cn0_dbhz=35.0, dwell_s=60, seed=4)
    resp = await client.post(f"{api}/gps/area", json={"points": puntos})
    body = resp.json()
    u = body["uncertainty"]
    evidencia["obtenido"] = (
        f"HTTP {resp.status_code}, método={u['method']}, área={body['analysis']['area_m2']:.1f} m² "
        f"± {u['area_u95_m2']:.1f} ({u['area_u95_pct']:.2f} %), cierre={u['closure_m']:.2f} m"
    )
    assert resp.status_code == 200
    assert u["method"] == "stop_and_go"
    assert body["analysis"]["area_m2"] == pytest.approx(6000, rel=0.03)
    assert u["area_u95_pct"] < 10
    assert abs(body["analysis"]["area_m2"] - 6000) <= u["area_u95_m2"]
    assert u["closure_m"] is not None
    assert u["k"] in (2.0, 2.5)  # 2,5 cuando la σ sale del error de cierre
    assert len(u["vertex_sigma_m"]) == 4
    assert body["discarded_by_signal"] == 0
    assert u["closure_consistent"] is not None


@pytest.mark.evidencia(
    id="BI-35",
    nombre="Recorrido exterior guarda la incertidumbre en la base de datos",
    requisito="RF-21",
    objetivo="Verificar que al crear un recorrido exterior se guarda la incertidumbre y se devuelve al consultarlo.",
    precondiciones="Usuario autenticado con un proyecto",
    entrada="POST /projects/{id}/surveys modo exterior con esquinas fijadas; luego GET /surveys/{id}",
    esperado="HTTP 201 y el GET devuelve la misma incertidumbre (método stop_and_go)",
)
async def test_recorrido_exterior_guarda_incertidumbre(auth_client, project, api, evidencia):
    creado = await auth_client.post(
        f"{api}/projects/{project['id']}/surveys",
        json={"name": "Terreno esquinas", "mode": "exterior", "gps_points": simulate_stop_and_go(TERRENO_100x60, seed=5)},
    )
    leido = await auth_client.get(f"{api}/surveys/{creado.json()['id']}")
    u = leido.json()["uncertainty"]
    evidencia["obtenido"] = (
        f"POST {creado.status_code}, GET {leido.status_code}: método={u['method']}, U95={u['area_u95_m2']:.1f} m²"
    )
    assert creado.status_code == 201
    assert leido.status_code == 200
    assert u == creado.json()["uncertainty"]
    assert u["method"] == "stop_and_go"


@pytest.mark.evidencia(
    id="BI-36",
    nombre="Recorrido interior no informa incertidumbre GPS",
    requisito="RF-21",
    objetivo="Verificar la compatibilidad: los recorridos interiores siguen funcionando y su incertidumbre es nula.",
    precondiciones="Usuario autenticado con un proyecto",
    entrada="POST /projects/{id}/surveys modo interior con esquinas",
    esperado="HTTP 201 y uncertainty = null",
)
async def test_recorrido_interior_sin_incertidumbre(auth_client, project, api, evidencia):
    resp = await auth_client.post(
        f"{api}/projects/{project['id']}/surveys",
        json={"name": "Aula", "mode": "interior", "corners": [[0, 0], [5, 0], [5, 4], [0, 4]]},
    )
    evidencia["obtenido"] = f"HTTP {resp.status_code}, uncertainty={resp.json().get('uncertainty')}"
    assert resp.status_code == 201
    assert resp.json()["uncertainty"] is None


@pytest.mark.evidencia(
    id="BI-37",
    nombre="Validación de los datos de señal GNSS",
    requisito="RF-20",
    objetivo="Verificar que la API rechaza datos de señal imposibles.",
    entrada="Lecturas con satellites = -1 y con cn0_dbhz = 120",
    esperado="HTTP 422 en ambos casos",
)
async def test_validacion_datos_senal(client, api, evidencia):
    puntos = simulate_gps_walk(TERRENO_100x60, seed=1)
    malos_sat = [{**p, "satellites": -1} for p in puntos]
    malos_cn0 = [{**p, "cn0_dbhz": 120} for p in puntos]
    r1 = await client.post(f"{api}/gps/area", json={"points": malos_sat})
    r2 = await client.post(f"{api}/gps/area", json={"points": malos_cn0})
    evidencia["obtenido"] = f"satellites=-1 → HTTP {r1.status_code}; cn0=120 → HTTP {r2.status_code}"
    assert r1.status_code == 422 and r2.status_code == 422
