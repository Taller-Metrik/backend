"""Transporte GPS, renombrar planos, validación GPS por referencia y calibraciones."""

import pytest

from app.services.gps import GpsReading, filter_speed_jumps
from tests.helpers import ORIGEN_TRUJILLO, TERRENO_100x60, simulate_gps_walk


@pytest.mark.evidencia(
    id="BU-59",
    nombre="Filtro de saltos según el transporte",
    requisito="RF-08",
    objetivo="Verificar que una lectura que implica una velocidad imposible para el transporte se descarta.",
    entrada="Caminata a 1.3 m/s con un salto de 80 m en 0.5 s",
    esperado="Caminata: salto descartado; Carro (hasta 60 m/s): sin descartes por debajo del límite",
)
def test_filtro_saltos(evidencia):
    lat0, lon0 = ORIGEN_TRUJILLO
    pts = [GpsReading(lat0 + i * 1.2e-5, lon0, 4.0, float(i)) for i in range(10)]
    pts.insert(5, GpsReading(lat0 + 4 * 1.2e-5 + 7.2e-4, lon0, 4.0, 4.5))
    _, d1 = filter_speed_jumps(pts, 3.0)
    _, d2 = filter_speed_jumps(pts, 200.0)
    evidencia["obtenido"] = f"caminata descartó {d1}, transporte rápido descartó {d2}"
    assert d1 >= 1 and d2 == 0


@pytest.mark.evidencia(
    id="BI-31",
    nombre="Renombrar un plano",
    requisito="RF-16",
    entrada="PATCH /surveys/{id} con nombre 'Aula 201 (corregida)'",
    esperado="HTTP 200 y el nombre nuevo al consultar",
)
async def test_renombrar_plano(auth_client, project, api, evidencia):
    s = (await auth_client.post(f"{api}/projects/{project['id']}/surveys",
                                json={"name": "Aula", "corners": [[0, 0], [5, 0], [5, 4], [0, 4], [0, 0]]})).json()
    r = await auth_client.patch(f"{api}/surveys/{s['id']}", json={"name": "Aula 201 (corregida)"})
    nuevo = (await auth_client.get(f"{api}/surveys/{s['id']}")).json()["name"]
    evidencia["obtenido"] = f"HTTP {r.status_code}, nombre='{nuevo}'"
    assert r.status_code == 200 and nuevo == "Aula 201 (corregida)"


@pytest.mark.evidencia(
    id="BI-32",
    nombre="Validación GPS contra una cancha de medidas oficiales",
    requisito="RF-14 (modo exterior)",
    objetivo="Verificar el margen de error de un terreno medido con GPS usando una referencia externa (sin wincha).",
    entrada="Recorrido en bicicleta de un terreno 100 × 60 m; referencia 'cancha' 6000 m² y 320 m",
    esperado="HTTP 200, error de área ≤ 5 % (cumple), error de perímetro calculado; GET devuelve lo mismo",
)
async def test_referencia_gps(auth_client, project, api, evidencia):
    s = (await auth_client.post(f"{api}/projects/{project['id']}/surveys", json={
        "name": "Cancha", "mode": "exterior", "transport": "bike",
        "gps_points": simulate_gps_walk(TERRENO_100x60, seed=3), "scale_denominator": 500})).json()
    r = await auth_client.put(f"{api}/surveys/{s['id']}/gps-reference",
                              json={"reference_type": "cancha", "real_area_m2": 6000, "real_perimeter_m": 320})
    body = r.json()
    again = await auth_client.get(f"{api}/surveys/{s['id']}/gps-reference")
    evidencia["obtenido"] = (f"HTTP {r.status_code}, área {body['measured_area_m2']:.0f} m² vs 6000 "
                             f"({body['area_error_pct']:.2f} %), perímetro {body['perimeter_error_pct']:.2f} %, cumple={body['meets_target']}")
    assert r.status_code == 200 and body["meets_target"] is True
    assert again.status_code == 200 and again.json()["area_error_pct"] == pytest.approx(body["area_error_pct"])


@pytest.mark.evidencia(
    id="BI-33",
    nombre="Guardar y consultar calibraciones de sensores",
    requisito="RF-09, calibración",
    entrada="POST /calibrations (largo de paso 0.68 m) y GET /calibrations?kind=step_length",
    esperado="HTTP 201 y la calibración aparece en la lista del usuario",
)
async def test_calibraciones(auth_client, api, evidencia):
    r = await auth_client.post(f"{api}/calibrations", json={"kind": "step_length", "device_id": "A25",
                                                             "params": {"step_length_m": 0.68, "steps": 15, "distance_m": 10.2}})
    lst = (await auth_client.get(f"{api}/calibrations", params={"kind": "step_length"})).json()
    evidencia["obtenido"] = f"HTTP {r.status_code}, en lista={len(lst)}, paso={lst[0]['params']['step_length_m']} m"
    assert r.status_code == 201 and len(lst) == 1 and lst[0]["params"]["step_length_m"] == 0.68
