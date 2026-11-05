"""Pruebas funcionales: validación de campo app vs wincha (CU-06)."""

import pytest

from tests.helpers import RECTANGULO_5x4, simulate_walk


@pytest.mark.evidencia(
    id="BF-07",
    nombre="Determinar el margen de error de un proyecto",
    requisito="CU-06 (RF-13, RF-14, RNF-01)",
    objetivo="Verificar el protocolo: varios recorridos del mismo ambiente, medidas con wincha y margen de error global.",
    precondiciones="Usuario autenticado; aula real de 5.00 × 4.00 m",
    entrada="3 recorridos simulados (ruido σ=3 cm, semillas distintas) + 2 lecturas de wincha por muro",
    esperado="Reporte del proyecto con 12 muros, error relativo medio ≤ 3 % (cumple RNF-01) y CSV descargable",
)
async def test_margen_de_error_proyecto(auth_client, project, api, evidencia):
    wincha = {"walls": [], "real_area_m2": 20.0}
    for seed in (11, 12, 13):
        s = (
            await auth_client.post(
                f"{api}/projects/{project['id']}/surveys",
                json={"name": f"Aula 201 - recorrido {seed - 10}", "points": simulate_walk(RECTANGULO_5x4, seed=seed)},
            )
        ).json()
        # Las paredes reales alternan 5 y 4 m; se asocian por orientación de cada muro medido
        wincha["walls"] = [
            {"wall_index": i, "readings_m": [5.0, 5.001] if abs(w - 5) < abs(w - 4) else [4.0, 4.001]}
            for i, w in enumerate(s["wall_lengths_m"])
        ]
        r = await auth_client.put(f"{api}/surveys/{s['id']}/references", json=wincha)
        assert r.status_code == 200

    reporte = (await auth_client.get(f"{api}/projects/{project['id']}/validation")).json()
    csv = await auth_client.get(f"{api}/projects/{project['id']}/validation.csv")
    rep = reporte["report"]
    evidencia["obtenido"] = (
        f"recorridos={reporte['surveys_validated']}, muros={rep['n']}, MAE={rep['mae_m'] * 100:.2f} cm, "
        f"RMSE={rep['rmse_m'] * 100:.2f} cm, sesgo={rep['bias_m'] * 100:+.2f} cm, "
        f"rel. medio={rep['mean_rel_error_pct']:.2f} %, cumple={rep['meets_target']}, CSV={csv.status_code}"
    )
    assert reporte["surveys_validated"] == 3 and rep["n"] == 12
    assert rep["mean_rel_error_pct"] <= 3.0 and rep["meets_target"] is True
    assert csv.status_code == 200
