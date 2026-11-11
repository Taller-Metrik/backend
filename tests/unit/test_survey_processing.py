"""Pruebas unitarias del procesamiento de recorridos (sin base de datos)."""

import pytest

from app.models.survey import SurveyMode
from app.schemas.project import SurveyCreate
from app.services.project_service import SurveyService
from tests.helpers import AMBIENTE_L, TERRENO_100x60, simulate_gps_walk, simulate_walk


def _process(payload: SurveyCreate) -> dict:
    return SurveyService.__new__(SurveyService)._process(payload)


@pytest.mark.evidencia(
    id="BU-26",
    nombre="Procesamiento de recorrido interior",
    requisito="RF-01, RF-05, RF-06",
    objetivo="Verificar que un recorrido interior se suaviza, se analiza y se le asigna escala.",
    entrada="Trazo simulado de ambiente en L (24 m²), sin escala indicada",
    esperado="6 vértices, 1 cóncavo, área ≈ 24 m², escala sugerida 1:25",
)
def test_procesar_interior(evidencia):
    r = _process(SurveyCreate(name="Aula L", points=simulate_walk(AMBIENTE_L)))
    evidencia["obtenido"] = (
        f"{len(r['vertices'])} vértices, cóncavos={r['concave_count']}, "
        f"área={r['area_m2']:.3f} m², escala=1:{r['scale_denominator']}"
    )
    assert len(r["vertices"]) == 6 and r["concave_count"] == 1
    assert r["area_m2"] == pytest.approx(24.0, rel=0.02)
    assert r["scale_denominator"] == 25


@pytest.mark.evidencia(
    id="BU-27",
    nombre="Procesamiento de plano importado sin suavizado",
    requisito="RF-11",
    objetivo="Verificar que los vértices de un plano importado se analizan tal cual, con la escala pedida.",
    entrada="Vértices del ambiente en L, modo 'imported', escala 1:100",
    esperado="Vértices idénticos, área 24 m², escala 1:100",
)
def test_procesar_importado(evidencia):
    r = _process(SurveyCreate(name="Plano", mode=SurveyMode.IMPORTED, corners=AMBIENTE_L, scale_denominator=100))
    evidencia["obtenido"] = f"vértices={r['vertices']}, área={r['area_m2']}, escala=1:{r['scale_denominator']}"
    assert r["vertices"] == [list(map(float, v)) for v in AMBIENTE_L]
    assert r["area_m2"] == pytest.approx(24.0)
    assert r["scale_denominator"] == 100


@pytest.mark.evidencia(
    id="BU-28",
    nombre="Validación de datos mínimos por modo",
    requisito="EX-04, EX-05",
    objetivo="Verificar que cada modo exige sus datos mínimos.",
    entrada="Interior sin trazo; exterior con 2 lecturas GPS; importado sin vértices",
    esperado="ValidationError en los tres casos",
)
def test_validacion_por_modo(evidencia):
    from pydantic import ValidationError

    casos = [
        {"name": "a", "mode": "interior"},
        {"name": "b", "mode": "exterior", "gps_points": [{"lat": 0, "lon": 0}, {"lat": 0, "lon": 1e-4}]},
        {"name": "c", "mode": "imported"},
    ]
    mensajes = []
    for caso in casos:
        with pytest.raises(ValidationError) as exc:
            SurveyCreate(**caso)
        mensajes.append(exc.value.errors()[0]["msg"])
    evidencia["obtenido"] = " | ".join(mensajes)


@pytest.mark.evidencia(
    id="BU-107",
    nombre="Exterior: se respetan las esquinas ajustadas en el celular",
    requisito="RF-08, RF-18, RF-21",
    objetivo=(
        "Verificar que, si el celular envía las esquinas ya ajustadas (poligonal con cierre repartido), el "
        "servidor las usa como vértices en vez de recalcularlas, con el origen en la primera lectura GPS, "
        "y les calcula su incertidumbre."
    ),
    entrada=(
        "Recorrido GPS del terreno 100×60 m (ruido 3 m) sin esquinas fijadas y 'corners' = las 4 esquinas "
        "reales en metros respecto de la primera lectura"
    ),
    esperado="Vértices = corners, área 6000 m², origen = primera lectura, incertidumbre con 4 σ de vértice",
)
def test_exterior_respeta_esquinas_del_celular(evidencia):
    gps = simulate_gps_walk(TERRENO_100x60, noise_m=3.0, seed=7)
    corners = [(1.5, -0.5), (101.5, -0.5), (101.5, 59.5), (1.5, 59.5)]
    r = _process(SurveyCreate(name="Terreno", mode=SurveyMode.EXTERIOR, gps_points=gps, corners=corners))
    u = r["uncertainty"]
    evidencia["obtenido"] = (
        f"vértices={r['vertices']}, área={r['area_m2']:.1f} m², origen={u['origin_latlon']}, "
        f"σ={[round(s, 2) for s in u['vertex_sigma_m']]}, U95 área={u['area_u95_m2']:.1f} m²"
    )
    assert r["vertices"] == [list(map(float, v)) for v in corners]
    assert r["area_m2"] == pytest.approx(6000.0)
    assert u["origin_latlon"] == [gps[0]["lat"], gps[0]["lon"]]
    assert len(u["vertex_sigma_m"]) == 4 and all(s > 0 for s in u["vertex_sigma_m"])
