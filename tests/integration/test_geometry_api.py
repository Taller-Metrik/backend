"""Pruebas de integración: endpoints de geometría (router + esquemas + servicios)."""

import pytest

from tests.helpers import AMBIENTE_L, RECTANGULO_5x4, simulate_walk


@pytest.mark.evidencia(
    id="BI-06",
    nombre="POST /geometry/analyze con ambiente en L",
    requisito="RF-06",
    objetivo="Verificar que el endpoint integra validación, cálculo y serialización del análisis.",
    entrada="Vértices del ambiente en L",
    esperado="HTTP 200, área 24, perímetro 22, 1 vértice cóncavo",
)
async def test_analyze_endpoint(client, api, evidencia):
    resp = await client.post(f"{api}/geometry/analyze", json={"vertices": AMBIENTE_L})
    body = resp.json()
    evidencia["obtenido"] = (
        f"HTTP {resp.status_code}, área={body['area_m2']}, perímetro={body['perimeter_m']}, "
        f"cóncavos={body['concave_vertices']}"
    )
    assert resp.status_code == 200
    assert body["area_m2"] == pytest.approx(24.0)
    assert body["perimeter_m"] == pytest.approx(22.0)
    assert len(body["concave_vertices"]) == 1


@pytest.mark.evidencia(
    id="BI-07",
    nombre="POST /geometry/analyze rechaza menos de 3 vértices",
    requisito="EX-05",
    objetivo="Verificar la validación de entrada del endpoint.",
    entrada="Dos vértices",
    esperado="HTTP 422",
)
async def test_analyze_invalido(client, api, evidencia):
    resp = await client.post(f"{api}/geometry/analyze", json={"vertices": [[0, 0], [1, 1]]})
    evidencia["obtenido"] = f"HTTP {resp.status_code}"
    assert resp.status_code == 422


@pytest.mark.evidencia(
    id="BI-08",
    nombre="POST /geometry/smooth con trazo ruidoso",
    requisito="RF-05",
    objetivo="Verificar que el endpoint suaviza un trazo de ~360 puntos y devuelve el análisis.",
    entrada="Trazo simulado del aula 5×4 m con ruido σ=3 cm",
    esperado="HTTP 200, 4 vértices, área ≈ 20 m²",
)
async def test_smooth_endpoint(client, api, evidencia):
    puntos = simulate_walk(RECTANGULO_5x4)
    resp = await client.post(f"{api}/geometry/smooth", json={"points": puntos})
    body = resp.json()
    evidencia["obtenido"] = (
        f"HTTP {resp.status_code}, entrada={body['input_points']} puntos, "
        f"vértices={len(body['vertices'])}, área={body['analysis']['area_m2']:.3f}"
    )
    assert resp.status_code == 200
    assert len(body["vertices"]) == 4
    assert body["analysis"]["area_m2"] == pytest.approx(20.0, rel=0.02)


@pytest.mark.evidencia(
    id="BI-09",
    nombre="POST /geometry/distance",
    requisito="RF-07",
    objetivo="Verificar el cálculo de distancias por la API.",
    entrada="A=(0,0), B=(30,40) (cuadra urbana)",
    esperado="Euclidiana 50 m, Manhattan 70 m, diferencia 20 m",
)
async def test_distance_endpoint(client, api, evidencia):
    resp = await client.post(f"{api}/geometry/distance", json={"a": [0, 0], "b": [30, 40]})
    body = resp.json()
    evidencia["obtenido"] = f"HTTP {resp.status_code}, {body}"
    assert resp.status_code == 200
    assert body == {"euclidean_m": 50.0, "manhattan_m": 70.0, "difference_m": 20.0}


@pytest.mark.evidencia(
    id="BI-10",
    nombre="POST /geometry/scale con escala inválida",
    requisito="RF-10",
    objetivo="Verificar que la API rechaza escalas no normalizadas.",
    entrada="lengths_m=[5], denominator=33",
    esperado="HTTP 422",
)
async def test_scale_invalida(client, api, evidencia):
    resp = await client.post(f"{api}/geometry/scale", json={"lengths_m": [5], "denominator": 33})
    evidencia["obtenido"] = f"HTTP {resp.status_code}: {resp.json()['detail']}"
    assert resp.status_code == 422
