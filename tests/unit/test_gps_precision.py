"""Pruebas unitarias de la mejora de precisión GPS (RF-18 a RF-21)."""

import math
import random

import pytest

from app.services.geometry import GeometryError, analyze
from app.services.gps import GpsReading, gps_polygon
from app.services.gps_precision import filter_by_signal, fix_vertex, sigma_from_accuracy, stop_and_go_vertices
from app.services.uncertainty import monte_carlo_uncertainty, polygon_uncertainty
from tests.helpers import ORIGEN_TRUJILLO, TERRENO_100x60, simulate_gps_walk, simulate_stop_and_go


def _r(items: list[dict]) -> list[GpsReading]:
    return [GpsReading(**i) for i in items]


@pytest.mark.evidencia(
    id="BU-61",
    nombre="Desviación estándar a partir de la precisión de Android",
    requisito="RF-21",
    objetivo="Verificar la conversión del radio del 68 % que reporta Android a desviación estándar por eje.",
    entrada="accuracy = 1,51 m y accuracy = 0 m",
    esperado="σ ≈ 1,00 m; con 0 m se aplica el piso de 0,3 m",
)
def test_sigma_desde_precision_android(evidencia):
    s, piso = sigma_from_accuracy(1.51), sigma_from_accuracy(0.0)
    evidencia["obtenido"] = f"σ(1,51)={s:.3f} m, σ(0)={piso:.2f} m"
    assert s == pytest.approx(1.0, abs=0.01)
    assert piso == pytest.approx(0.3)


@pytest.mark.evidencia(
    id="BU-62",
    nombre="Filtro por calidad de señal GNSS",
    requisito="RF-20",
    objetivo="Verificar que se descartan lecturas con pocos satélites o señal débil y se conservan las que no traen esos datos.",
    entrada="4 lecturas: 8 sat/35 dB-Hz, 4 sat/35 dB-Hz, 8 sat/22 dB-Hz y sin datos de señal",
    esperado="Se conservan 2 (la buena y la sin datos) y se descartan 2",
)
def test_filtro_por_senal(evidencia):
    base = {"lat": ORIGEN_TRUJILLO[0], "lon": ORIGEN_TRUJILLO[1], "accuracy_m": 3.0}
    lecturas = _r([
        {**base, "satellites": 8, "cn0_dbhz": 35.0},
        {**base, "satellites": 4, "cn0_dbhz": 35.0},
        {**base, "satellites": 8, "cn0_dbhz": 22.0},
        base,
    ])
    kept, dropped = filter_by_signal(lecturas)
    evidencia["obtenido"] = f"conservadas={len(kept)}, descartadas={dropped}"
    assert len(kept) == 2 and dropped == 2
    assert kept[1].satellites is None


@pytest.mark.evidencia(
    id="BU-63",
    nombre="Fijación de una esquina con descarte de lecturas atípicas",
    requisito="RF-18",
    objetivo="Verificar el promedio ponderado 1/σ² y el descarte de lecturas fuera del radio del 95 %.",
    entrada="30 lecturas quietas en (10, 20) con σ=1,5 m y 3 saltos de 25 m",
    esperado="Esquina a menos de 0,8 m del punto real y los 3 saltos descartados",
)
def test_fijar_esquina_descarta_atipicos(evidencia):
    rng = random.Random(3)
    pts = [(10 + rng.gauss(0, 1.5), 20 + rng.gauss(0, 1.5)) for _ in range(30)] + [(35, 20), (10, -5), (-15, 20)]
    fix = fix_vertex(pts, [1.5] * len(pts), duration_s=33)
    err = math.dist(fix.point, (10, 20))
    evidencia["obtenido"] = (
        f"esquina=({fix.point[0]:.2f}, {fix.point[1]:.2f}), error={err:.2f} m, "
        f"descartadas={fix.rejected}, σ={fix.sigma_m:.2f} m"
    )
    assert err < 0.8
    assert fix.rejected == 3
    assert fix.used == 30


@pytest.mark.evidencia(
    id="BU-64",
    nombre="Plano GPS con esquinas fijadas (stop-and-go)",
    requisito="RF-18",
    objetivo="Verificar que el polígono se arma con las esquinas fijadas.",
    entrada="Terreno 100×60 m: 30 s quieto por esquina (σ=1,5 m, sesgo 1 m) y caminata con ruido de 3 m",
    esperado="Método stop_and_go, 4 vértices, área 6000 m² ± 3 % y el área real dentro de ± U95",
)
def test_poligono_stop_and_go(evidencia):
    poly = gps_polygon(_r(simulate_stop_and_go(TERRENO_100x60, seed=4)))
    area = analyze(poly.vertices).area_m2
    evidencia["obtenido"] = (
        f"método={poly.method}, vértices={len(poly.vertices)}, área={area:.1f} m², cierre={poly.closure_m:.2f} m"
    )
    assert poly.method == "stop_and_go"
    assert len(poly.vertices) == 4
    assert area == pytest.approx(6000, rel=0.03)
    assert abs(area - 6000) <= poly.uncertainty.area_u95_m2


@pytest.mark.evidencia(
    id="BU-65",
    nombre="Cierre del recorrido como estimador del error",
    requisito="RF-19",
    objetivo="Verificar que al volver a fijar la primera esquina se mide el error de cierre y se usa como piso de σ.",
    entrada="Stop-and-go sin sesgo, σ=0,3 m, y la primera esquina vuelta a fijar 2 m al este",
    esperado="Cierre ≈ 2 m y σ de cada esquina ≥ 1 m (cierre / 2)",
)
def test_cierre_estima_sigma(evidencia):
    lecturas = _r(simulate_stop_and_go(TERRENO_100x60, sigma_m=0.3, bias_m=0.0, closure_offset_m=2.0, seed=2))
    sg = stop_and_go_vertices(lecturas, origin=ORIGEN_TRUJILLO)
    evidencia["obtenido"] = f"cierre={sg.closure_m:.2f} m, σ={[round(s, 2) for s in sg.sigmas_m]}"
    assert sg.closure_m == pytest.approx(2.0, abs=0.3)
    assert len(sg.vertices) == 4
    assert min(sg.sigmas_m) >= 0.95


@pytest.mark.evidencia(
    id="BU-66",
    nombre="Incertidumbre analítica del área de un cuadrado",
    requisito="RF-21",
    objetivo="Verificar σ_A² = ¼ Σ σᵢ² dᵢ² con el caso cerrado σ_A = √2·σ·L.",
    entrada="Cuadrado de 100 m de lado, σ = 1 m por vértice, k = 2",
    esperado="σ_A = 141,4 m², U95 = 282,8 m² (2,83 %); σ_P = 2√2 m",
)
def test_incertidumbre_cuadrado(evidencia):
    u = polygon_uncertainty([(0, 0), (100, 0), (100, 100), (0, 100)], [1.0] * 4)
    evidencia["obtenido"] = (
        f"σ_A={u.area_sigma_m2:.1f} m², U95={u.area_u95_m2:.1f} m² ({u.area_u95_pct:.2f} %), "
        f"σ_P={u.perimeter_sigma_m:.3f} m, U95_P={u.perimeter_u95_m:.2f} m"
    )
    assert u.area_sigma_m2 == pytest.approx(math.sqrt(2) * 100, rel=1e-6)
    assert u.area_u95_m2 == pytest.approx(2 * math.sqrt(2) * 100, rel=1e-6)
    assert u.area_u95_pct == pytest.approx(2.828, abs=0.01)
    assert u.perimeter_sigma_m == pytest.approx(2 * math.sqrt(2), rel=1e-6)
    assert u.k == 2.0


@pytest.mark.evidencia(
    id="BU-67",
    nombre="Fórmula analítica validada con Monte Carlo",
    requisito="RF-21",
    objetivo="Verificar que la propagación lineal coincide con 4000 simulaciones Monte Carlo en un polígono irregular.",
    entrada="Polígono irregular de 6 vértices con σ entre 0,8 y 2,5 m",
    esperado="σ_A y σ_P analíticos dentro de ±8 % de Monte Carlo",
)
def test_analitico_vs_montecarlo(evidencia):
    poly = [(0, 0), (120, -10), (150, 60), (90, 110), (20, 95), (-15, 40)]
    sigmas = [0.8, 1.2, 2.5, 1.0, 1.7, 2.0]
    u = polygon_uncertainty(poly, sigmas)
    mc_area, mc_per = monte_carlo_uncertainty(poly, sigmas, runs=4000, seed=7)
    evidencia["obtenido"] = (
        f"σ_A analítico={u.area_sigma_m2:.1f}, Monte Carlo={mc_area:.1f} m² | "
        f"σ_P analítico={u.perimeter_sigma_m:.2f}, Monte Carlo={mc_per:.2f} m"
    )
    assert u.area_sigma_m2 == pytest.approx(mc_area, rel=0.08)
    assert u.perimeter_sigma_m == pytest.approx(mc_per, rel=0.08)


@pytest.mark.evidencia(
    id="BU-68",
    nombre="Cobertura real de la incertidumbre al 95 %",
    requisito="RF-21",
    objetivo="Verificar que el intervalo área ± U95 contiene el área real en al menos el 90 % de recorridos simulados.",
    entrada="60 recorridos stop-and-go del terreno 100×60 m con semillas distintas",
    esperado="Cobertura ≥ 90 %",
)
def test_cobertura_incertidumbre(evidencia):
    dentro = 0
    for seed in range(60):
        poly = gps_polygon(_r(simulate_stop_and_go(TERRENO_100x60, seed=100 + seed)))
        if abs(analyze(poly.vertices).area_m2 - 6000) <= poly.uncertainty.area_u95_m2:
            dentro += 1
    cobertura = dentro / 60
    evidencia["obtenido"] = f"cobertura={cobertura:.0%} ({dentro}/60)"
    assert cobertura >= 0.9


@pytest.mark.evidencia(
    id="BU-69",
    nombre="Recorrido continuo sigue funcionando y reporta incertidumbre",
    requisito="RF-08 / RF-21",
    objetivo="Verificar la compatibilidad: sin esquinas fijadas se usa el método continuo con una incertidumbre conservadora.",
    entrada="Recorrido continuo del terreno 100×60 m (ruido 3 m) sin vertex_id",
    esperado="Método continuous, área 6000 ± 5 % y el área real dentro de ± U95",
)
def test_recorrido_continuo_compatible(evidencia):
    poly = gps_polygon(_r(simulate_gps_walk(TERRENO_100x60, seed=3)))
    area = analyze(poly.vertices).area_m2
    u = poly.uncertainty
    evidencia["obtenido"] = (
        f"método={poly.method}, área={area:.1f} m², U95={u.area_u95_m2:.1f} m² ({u.area_u95_pct:.1f} %)"
    )
    assert poly.method == "continuous"
    assert poly.closure_m is None
    assert area == pytest.approx(6000, rel=0.05)
    assert abs(area - 6000) <= u.area_u95_m2


@pytest.mark.evidencia(
    id="BU-70",
    nombre="Descarte por señal dentro del cálculo del polígono",
    requisito="RF-20 / EX-04",
    objetivo="Verificar que gps_polygon descarta las lecturas con señal insuficiente antes de calcular.",
    entrada="Recorrido stop-and-go donde todas las lecturas reportan 4 satélites",
    esperado="Error: no quedan lecturas válidas (EX-04)",
)
def test_poligono_descarta_por_senal(evidencia):
    with pytest.raises(GeometryError) as exc:
        gps_polygon(_r(simulate_stop_and_go(TERRENO_100x60, satellites=4, seed=1)))
    evidencia["obtenido"] = str(exc.value)
    assert "EX-04" in str(exc.value)


@pytest.mark.evidencia(
    id="BU-71",
    nombre="Cierre incoherente con la σ declarada",
    requisito="RF-19 / RF-21",
    objetivo="Verificar que un cierre mayor al percentil 95 esperado se marca como no creíble y amplía k a 2,5.",
    entrada="Stop-and-go sin sesgo, σ=0,3 m, primera esquina vuelta a fijar 4 m al este",
    esperado="closure_consistent = False, σ ≥ 4/√π ≈ 2,26 m y k = 2,5",
)
def test_cierre_incoherente(evidencia):
    lecturas = _r(simulate_stop_and_go(TERRENO_100x60, sigma_m=0.3, bias_m=0.0, closure_offset_m=4.0, seed=2))
    poly = gps_polygon(lecturas)
    evidencia["obtenido"] = (
        f"cierre={poly.closure_m:.2f} m, coherente={poly.closure_consistent}, "
        f"σ mín={min(poly.vertex_sigmas_m):.2f} m, k={poly.uncertainty.k}"
    )
    assert poly.closure_consistent is False
    assert min(poly.vertex_sigmas_m) >= 4.0 / math.sqrt(math.pi) - 0.15
    assert poly.uncertainty.k == 2.5


@pytest.mark.evidencia(
    id="BU-72",
    nombre="Error que no se reduce al promediar",
    requisito="RF-18",
    objetivo="Verificar que una esquina medida mucho tiempo nunca baja de σ_b = 0,5 m (multitrayecto, ionosfera).",
    entrada="300 lecturas quietas (5 minutos) con σ=0,3 m",
    esperado="σ del vértice ≥ 0,5 m",
)
def test_piso_no_promediable(evidencia):
    rng = random.Random(9)
    pts = [(rng.gauss(0, 0.3), rng.gauss(0, 0.3)) for _ in range(300)]
    fix = fix_vertex(pts, [0.3] * 300, duration_s=300)
    evidencia["obtenido"] = f"σ={fix.sigma_m:.3f} m"
    assert fix.sigma_m >= 0.5
