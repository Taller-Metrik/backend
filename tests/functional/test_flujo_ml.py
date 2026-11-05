"""Pruebas funcionales: el ML mejora la medida frente a la wincha (RF-15 + RF-14)."""

import pytest

# Recorrido "real": la persona camina ~4 cm separada de las paredes → muros más cortos.
CORNERS_CORTOS = [(0.04, 0.04), (4.96, 0.04), (4.96, 3.96), (0.04, 3.96), (0.04, 0.04)]


@pytest.mark.evidencia(
    id="BF-08",
    nombre="Corrección por ML reduce el error frente a la wincha",
    requisito="RF-15, RF-14",
    objetivo="Verificar el flujo: medir → analizar con ML → comparar medida original y corregida con la wincha.",
    precondiciones="Aula real de 5.00 × 4.00 m; la app midió 4.92 × 3.92 m (sesgo por separación de la pared)",
    entrada="Recorrido con esquinas marcadas, captura ARCore de 20 s; wincha 5.00/4.00 m",
    esperado="Error medio absoluto con corrección < sin corrección; recorrido clasificado como confiable",
)
async def test_ml_reduce_error(auth_client, project, api, evidencia):
    s = (
        await auth_client.post(
            f"{api}/projects/{project['id']}/surveys",
            json={"name": "Aula 305", "corners": CORNERS_CORTOS,
                  "capture": {"odometry": "arcore", "tracking_loss_s": 0, "duration_s": 20}},
        )
    ).json()
    ml = (await auth_client.get(f"{api}/surveys/{s['id']}/ml")).json()
    reales = [5.0 if i % 2 == 0 else 4.0 for i in range(4)]
    antes = sum(abs(w["measured_m"] - r) for w, r in zip(ml["walls"], reales, strict=True)) / 4
    despues = sum(abs(w["corrected_m"] - r) for w, r in zip(ml["walls"], reales, strict=True)) / 4
    evidencia["obtenido"] = (
        f"error medio sin corrección={antes * 100:.2f} cm, con corrección={despues * 100:.2f} cm, "
        f"P(confiable)={ml['reliability_probability']:.3f} → {ml['recommendation']}"
    )
    assert despues < antes
    assert ml["reliable"] is True
