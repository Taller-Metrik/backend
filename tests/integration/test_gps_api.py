"""Pruebas de integración: endpoints GPS y recorrido exterior con base de datos."""

import pytest

from app.models.survey import Survey
from tests.helpers import ORIGEN_TRUJILLO, TERRENO_100x60, simulate_gps_walk, simulate_static_gps


@pytest.mark.evidencia(
    id="BI-16",
    nombre="POST /gps/error con punto de referencia",
    requisito="RF-09",
    objetivo="Verificar que la API calcula el margen de error y recomienda no calibrar con buena señal.",
    entrada="200 lecturas estáticas σ=2 m y el punto real",
    esperado="HTTP 200, CEP < 8 m, needs_calibration=False y recomendación",
)
async def test_gps_error_endpoint(client, api, evidencia):
    resp = await client.post(
        f"{api}/gps/error",
        json={
            "readings": simulate_static_gps(200, sigma_m=2.0),
            "reference": {"lat": ORIGEN_TRUJILLO[0], "lon": ORIGEN_TRUJILLO[1]},
        },
    )
    body = resp.json()
    evidencia["obtenido"] = (
        f"HTTP {resp.status_code}, CEP={body['cep50_m']:.2f} m, 2DRMS={body['two_drms_m']:.2f} m, "
        f"calibrar={body['needs_calibration']} → {body['recommendation']}"
    )
    assert resp.status_code == 200
    assert body["cep50_m"] < 8 and body["needs_calibration"] is False


@pytest.mark.evidencia(
    id="BI-17",
    nombre="POST /gps/area de un terreno",
    requisito="RF-08",
    objetivo="Verificar la integración filtro → Kalman/RTS → simplificación → análisis por la API.",
    entrada="Recorrido GPS simulado de un terreno 100×60 m con lecturas atípicas",
    esperado="HTTP 200, área 6000 m² ± 5 %, lecturas atípicas descartadas, escala 1:500",
)
async def test_gps_area_endpoint(client, api, evidencia):
    resp = await client.post(f"{api}/gps/area", json={"points": simulate_gps_walk(TERRENO_100x60, outlier_every=15)})
    body = resp.json()
    evidencia["obtenido"] = (
        f"HTTP {resp.status_code}, área={body['analysis']['area_m2']:.1f} m², "
        f"perímetro={body['analysis']['perimeter_m']:.1f} m, descartadas={body['discarded_readings']}, {body['scale']}"
    )
    assert resp.status_code == 200
    assert body["analysis"]["area_m2"] == pytest.approx(6000, rel=0.05)
    assert body["discarded_readings"] > 0 and body["scale"] == "1:500"


@pytest.mark.evidencia(
    id="BI-18",
    nombre="Recorrido exterior guardado en el proyecto",
    requisito="RF-08",
    objetivo="Verificar que un recorrido en modo exterior se procesa con GPS y se persiste.",
    entrada="POST /projects/{id}/surveys con mode=exterior y lecturas GPS, escala 1:500",
    esperado="HTTP 201, modo exterior en BD, lecturas GPS guardadas, área ≈ 6000 m²",
)
async def test_recorrido_exterior(auth_client, project, db_session, api, evidencia):
    resp = await auth_client.post(
        f"{api}/projects/{project['id']}/surveys",
        json={
            "name": "Cancha",
            "mode": "exterior",
            "gps_points": simulate_gps_walk(TERRENO_100x60, seed=3),
            "scale_denominator": 500,
        },
    )
    guardado = await db_session.get(Survey, resp.json()["id"])
    evidencia["obtenido"] = (
        f"HTTP {resp.status_code}, modo={guardado.mode.value}, lecturas={len(guardado.gps_points)}, "
        f"área={guardado.area_m2:.1f} m²"
    )
    assert resp.status_code == 201
    assert guardado.mode.value == "exterior" and len(guardado.gps_points) > 100
    assert guardado.area_m2 == pytest.approx(6000, rel=0.05)


@pytest.mark.evidencia(
    id="BI-56",
    nombre="Recorrido exterior guarda el trazo de pantalla y cada etapa del procesamiento",
    requisito="RF-08",
    objetivo="Verificar que el trazo antes del suavizado y las etapas del celular se guardan para medir dónde nace el error.",
    entrada="POST exterior con lecturas GPS, 'points' (trazo en pantalla) y 'stages' (esquinas tocadas, limpias, poligonal)",
    esperado="HTTP 201, raw_points = trazo enviado, processing_stages con las 3 etapas; etapa con nombre inválido → 422",
)
async def test_recorrido_exterior_guarda_trazo_y_etapas(auth_client, project, db_session, api, evidencia):
    trazo = [[0.0, 0.0], [50.0, 0.3], [100.0, -0.2], [100.2, 60.0], [0.1, 60.2], [0.0, 0.4]]
    etapas = {
        "esquinas_tocadas": [[0, 0], [100, 0], [100.5, 1.0], [100, 60], [0, 60]],
        "esquinas_limpias": [[0, 0], [100, 0], [100, 60], [0, 60]],
        "poligonal": [[0, 0], [99.8, 0.1], [100.1, 59.9], [0.2, 60]],
    }
    base = {"name": "Parque", "mode": "exterior", "gps_points": simulate_gps_walk(TERRENO_100x60, seed=3)}
    resp = await auth_client.post(f"{api}/projects/{project['id']}/surveys", json={**base, "points": trazo, "stages": etapas})
    guardado = await db_session.get(Survey, resp.json()["id"])
    malo = await auth_client.post(
        f"{api}/projects/{project['id']}/surveys", json={**base, "stages": {"<script>": [[0, 0]]}}
    )
    evidencia["obtenido"] = (
        f"HTTP {resp.status_code}, trazo guardado={len(guardado.raw_points)} puntos, "
        f"etapas={sorted((guardado.processing_stages or {}).keys())}, nombre inválido → HTTP {malo.status_code}"
    )
    assert resp.status_code == 201
    assert guardado.raw_points == trazo
    assert guardado.processing_stages == {k: [[float(x), float(y)] for x, y in v] for k, v in etapas.items()}
    assert guardado.area_m2 == pytest.approx(6000, rel=0.05)  # el trazo no cambia el resultado exterior
    assert malo.status_code == 422
