"""Pruebas funcionales: caso de uso de medición exterior con GPS (CU-02)."""

import pytest

from tests.helpers import ORIGEN_TRUJILLO, TERRENO_100x60, simulate_gps_walk, simulate_static_gps


@pytest.mark.evidencia(
    id="BF-05",
    nombre="Medir el área de un terreno con GPS, con calibración condicional",
    requisito="CU-02 (RF-08, RF-09, RF-10)",
    objetivo="Verificar el flujo: comprobar precisión GPS → calibrar si hace falta → recorrer → área a escala 1:500.",
    precondiciones="Usuario autenticado con un proyecto",
    entrada="1) 30 lecturas iniciales con σ=15 m  2) 60 lecturas tras calibrar con σ=2 m  3) recorrido del terreno 100×60 m",
    esperado="Primero pide calibrar, luego no; recorrido guardado con área 6000 m² ± 5 % y escala 1:500",
)
async def test_medicion_exterior_completa(auth_client, project, api, evidencia):
    ref = {"lat": ORIGEN_TRUJILLO[0], "lon": ORIGEN_TRUJILLO[1]}
    inicial = (await auth_client.post(
        f"{api}/gps/error", json={"readings": simulate_static_gps(30, sigma_m=15, seed=2), "reference": ref}
    )).json()
    calibrado = (await auth_client.post(
        f"{api}/gps/error", json={"readings": simulate_static_gps(60, sigma_m=2, seed=5), "reference": ref}
    )).json()
    recorrido = await auth_client.post(
        f"{api}/projects/{project['id']}/surveys",
        json={"name": "Terreno UPAO", "mode": "exterior", "gps_points": simulate_gps_walk(TERRENO_100x60, seed=6),
              "scale_denominator": 500},
    )
    plano = recorrido.json()
    evidencia["obtenido"] = (
        f"inicial: CEP={inicial['cep50_m']:.1f} m calibrar={inicial['needs_calibration']} | "
        f"tras calibrar: CEP={calibrado['cep50_m']:.1f} m calibrar={calibrado['needs_calibration']} | "
        f"área={plano['area_m2']:.1f} m², escala=1:{plano['scale_denominator']}"
    )
    assert inicial["needs_calibration"] is True
    assert calibrado["needs_calibration"] is False
    assert recorrido.status_code == 201
    assert plano["area_m2"] == pytest.approx(6000, rel=0.05)
    assert plano["scale_denominator"] == 500
