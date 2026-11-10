"""Pruebas funcionales: caso de uso de medición exterior con GPS (CU-02)."""

import pytest

from tests.helpers import ORIGEN_TRUJILLO, TERRENO_100x60, simulate_gps_walk, simulate_static_gps, simulate_stop_and_go


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


@pytest.mark.evidencia(
    id="BF-09",
    nombre="Medir un terreno fijando esquinas y comparar con el recorrido continuo",
    requisito="CU-02 (RF-18, RF-19, RF-21)",
    objetivo="Verificar que fijar las esquinas (stop-and-go) reduce la incertidumbre del área frente al recorrido continuo.",
    precondiciones="Usuario autenticado con un proyecto",
    entrada="El mismo terreno 100×60 m medido 1) caminando sin parar y 2) quieto 30 s en cada esquina y volviendo al inicio",
    esperado="Ambos recorridos guardados; el de esquinas fijadas tiene menor U95 del área, menor a 5 %, y cierre informado",
)
async def test_esquinas_fijadas_reducen_incertidumbre(auth_client, project, api, evidencia):
    async def medir(nombre: str, puntos: list[dict]) -> dict:
        resp = await auth_client.post(
            f"{api}/projects/{project['id']}/surveys",
            json={"name": nombre, "mode": "exterior", "gps_points": puntos, "scale_denominator": 500},
        )
        assert resp.status_code == 201, resp.text
        return resp.json()

    continuo = await medir("Terreno continuo", simulate_gps_walk(TERRENO_100x60, seed=8))
    fijado = await medir("Terreno esquinas", simulate_stop_and_go(TERRENO_100x60, seed=8))
    uc, uf = continuo["uncertainty"], fijado["uncertainty"]
    evidencia["obtenido"] = (
        f"continuo: área={continuo['area_m2']:.1f} ± {uc['area_u95_m2']:.1f} m² ({uc['area_u95_pct']:.1f} %) | "
        f"esquinas: área={fijado['area_m2']:.1f} ± {uf['area_u95_m2']:.1f} m² ({uf['area_u95_pct']:.1f} %), "
        f"cierre={uf['closure_m']:.2f} m"
    )
    assert uc["method"] == "continuous" and uf["method"] == "stop_and_go"
    assert uf["area_u95_m2"] < uc["area_u95_m2"]
    assert uf["area_u95_pct"] < 5
    assert uf["closure_m"] is not None
    assert abs(fijado["area_m2"] - 6000) <= uf["area_u95_m2"]
