"""Pruebas funcionales: del trazo crudo al plano a escala (CU-01, CU-03, CU-05)."""

import pytest

from tests.helpers import AMBIENTE_L, simulate_walk


@pytest.mark.evidencia(
    id="BF-02",
    nombre="Del recorrido ruidoso al plano a escala 1:50",
    requisito="RF-05, RF-06, RF-10",
    objetivo="Verificar el caso de uso: recorrer un ambiente en L, suavizar y obtener cotas a escala.",
    precondiciones="Trazo simulado de un ambiente en L (24 m²) con ruido σ=3 cm, rotado 20°",
    entrada="POST /geometry/smooth → POST /geometry/scale (1:50)",
    esperado="Plano de 6 muros a 90°/270°, área 24 m² ± 2 %, cotas en mm = metros × 20",
)
async def test_recorrido_a_plano_escala(client, api, evidencia):
    r1 = await client.post(f"{api}/geometry/smooth", json={"points": simulate_walk(AMBIENTE_L, seed=5)})
    plano = r1.json()
    muros = plano["analysis"]["wall_lengths_m"]
    r2 = await client.post(f"{api}/geometry/scale", json={"lengths_m": muros, "denominator": 50})
    cotas = r2.json()["paper_mm"]

    evidencia["obtenido"] = (
        f"muros={[round(m, 2) for m in muros]} m, área={plano['analysis']['area_m2']:.2f} m², "
        f"cotas 1:50={[round(c, 1) for c in cotas]} mm"
    )
    assert r1.status_code == r2.status_code == 200
    assert len(muros) == 6
    assert sorted(round(a) for a in plano["analysis"]["interior_angles_deg"]) == [90, 90, 90, 90, 90, 270]
    assert plano["analysis"]["area_m2"] == pytest.approx(24.0, rel=0.02)
    assert cotas == pytest.approx([m * 20 for m in muros])


@pytest.mark.evidencia(
    id="BF-03",
    nombre="Medición sobre un plano importado",
    requisito="RF-11",
    objetivo="Verificar el caso de uso: calibrar una imagen de plano y medir un ambiente sobre ella.",
    precondiciones="Imagen de plano donde 250 px = 5 m",
    entrada="Calibración con (0,0)-(250,0)=5 m y vértices de un rectángulo de 250×200 px",
    esperado="0.02 m/px, ambiente de 5×4 m y 20 m²",
)
async def test_medicion_plano_importado(client, api, evidencia):
    resp = await client.post(
        f"{api}/geometry/calibrate-image",
        json={
            "p1_px": [0, 0],
            "p2_px": [250, 0],
            "real_distance_m": 5,
            "points_px": [[0, 0], [250, 0], [250, 200], [0, 200]],
        },
    )
    body = resp.json()
    evidencia["obtenido"] = (
        f"HTTP {resp.status_code}, {body['meters_per_pixel']} m/px, área={body['analysis']['area_m2']} m², "
        f"muros={body['analysis']['wall_lengths_m']}"
    )
    assert resp.status_code == 200
    assert body["meters_per_pixel"] == pytest.approx(0.02)
    assert body["analysis"]["area_m2"] == pytest.approx(20.0)
