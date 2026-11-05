"""Pruebas unitarias del modo exterior GPS (RF-08, RF-09)."""

import math

import pytest

from app.services.geometry import GeometryError, analyze
from app.services.gps import (
    GpsReading,
    error_metrics,
    filter_by_accuracy,
    gps_polygon,
    haversine,
    kalman_smooth,
    to_enu,
)
from tests.helpers import ORIGEN_TRUJILLO, TERRENO_100x60, simulate_gps_walk, simulate_static_gps


def _r(items: list[dict]) -> list[GpsReading]:
    return [GpsReading(**i) for i in items]


@pytest.mark.evidencia(
    id="BU-29",
    nombre="Distancia Haversine de 1° de latitud",
    requisito="RF-08",
    objetivo="Verificar la fórmula de Haversine con un valor conocido.",
    entrada="(0°, 0°) → (1°, 0°)",
    esperado="≈ 111 195 m",
)
def test_haversine(evidencia):
    d = haversine((0, 0), (1, 0))
    evidencia["obtenido"] = f"{d:.1f} m"
    assert d == pytest.approx(111_195, rel=1e-4)


@pytest.mark.evidencia(
    id="BU-30",
    nombre="Proyección ENU consistente con Haversine",
    requisito="RF-08",
    objetivo="Verificar que la proyección local en metros coincide con la distancia geodésica en áreas pequeñas.",
    entrada="Punto a 300 m al este y 400 m al norte del origen (Trujillo)",
    esperado="Distancia ENU = Haversine = 500 m (diferencia < 0.1 %)",
)
def test_enu_vs_haversine(evidencia):
    lat0, lon0 = ORIGEN_TRUJILLO
    lat = lat0 + math.degrees(400 / 6_371_000)
    lon = lon0 + math.degrees(300 / (6_371_000 * math.cos(math.radians(lat0))))
    (x, y) = to_enu([GpsReading(lat0, lon0), GpsReading(lat, lon)])[1]
    h = haversine((lat0, lon0), (lat, lon))
    evidencia["obtenido"] = f"ENU=({x:.2f}, {y:.2f}) → {math.hypot(x, y):.2f} m; Haversine={h:.2f} m"
    assert math.hypot(x, y) == pytest.approx(500, rel=1e-3)
    assert math.hypot(x, y) == pytest.approx(h, rel=1e-3)


@pytest.mark.evidencia(
    id="BU-31",
    nombre="Filtrado de lecturas GPS imprecisas",
    requisito="RF-08 / EX-04",
    objetivo="Verificar que se descartan las lecturas con precisión peor que el umbral.",
    entrada="Recorrido con una lectura atípica (30 m) cada 10",
    esperado="Se descartan exactamente las lecturas atípicas",
)
def test_filtrado(evidencia):
    lecturas = _r(simulate_gps_walk(TERRENO_100x60, outlier_every=10))
    validas, descartadas = filter_by_accuracy(lecturas, 10.0)
    atipicas = sum(1 for r in lecturas if r.accuracy_m > 10)
    evidencia["obtenido"] = f"total={len(lecturas)}, válidas={len(validas)}, descartadas={descartadas}"
    assert descartadas == atipicas > 0


@pytest.mark.evidencia(
    id="BU-32",
    nombre="Filtro de Kalman reduce el ruido",
    requisito="RF-08",
    objetivo="Verificar que el filtro de Kalman acerca la trayectoria a la real.",
    entrada="Caminata recta de 100 m a 1 m/s con ruido σ=3 m",
    esperado="Error medio filtrado < error medio crudo",
)
def test_kalman(evidencia):
    import random

    rng = random.Random(3)
    real = [(float(t), 0.0) for t in range(100)]
    ruidoso = [(x + rng.gauss(0, 3), y + rng.gauss(0, 3)) for x, y in real]
    filtrado = kalman_smooth(ruidoso, [float(t) for t in range(100)], [3.0] * 100)
    e_crudo = sum(math.dist(a, b) for a, b in zip(real, ruidoso, strict=True)) / 100
    e_filtrado = sum(math.dist(a, b) for a, b in zip(real, filtrado, strict=True)) / 100
    evidencia["obtenido"] = f"error medio crudo={e_crudo:.2f} m, filtrado={e_filtrado:.2f} m"
    assert e_filtrado < e_crudo * 0.7


@pytest.mark.evidencia(
    id="BU-33",
    nombre="Margen de error GPS con precisión buena",
    requisito="RF-09",
    objetivo="Verificar CEP, R95 y 2DRMS con lecturas estáticas y punto real conocido; sin calibración.",
    entrada="300 lecturas quietas con σ=2 m por eje alrededor del punto real",
    esperado="CEP ≈ 1.18·σ ≈ 2.4 m (±20 %), 2DRMS ≈ 5.7 m, needs_calibration=False",
)
def test_error_gps_bueno(evidencia):
    m = error_metrics(_r(simulate_static_gps(300, sigma_m=2.0)), reference=ORIGEN_TRUJILLO)
    evidencia["obtenido"] = (
        f"CEP={m.cep50_m:.2f} m, R95={m.r95_m:.2f} m, DRMS={m.drms_m:.2f} m, 2DRMS={m.two_drms_m:.2f} m, "
        f"calibrar={m.needs_calibration}"
    )
    assert m.cep50_m == pytest.approx(1.1774 * 2.0, rel=0.2)
    assert m.two_drms_m == pytest.approx(2 * math.sqrt(2) * 2.0, rel=0.2)
    assert m.needs_calibration is False


@pytest.mark.evidencia(
    id="BU-34",
    nombre="Calibración requerida con error inicial alto",
    requisito="RF-09",
    objetivo="Verificar que se pide calibración cuando el CEP supera el umbral (8 m).",
    entrada="60 lecturas quietas con σ=12 m (señal degradada)",
    esperado="needs_calibration=True",
)
def test_error_gps_malo(evidencia):
    m = error_metrics(_r(simulate_static_gps(60, sigma_m=12.0, seed=4)), reference=ORIGEN_TRUJILLO)
    evidencia["obtenido"] = f"CEP={m.cep50_m:.2f} m, calibrar={m.needs_calibration}"
    assert m.needs_calibration is True


@pytest.mark.evidencia(
    id="BU-35",
    nombre="Área y perímetro de un terreno con GPS",
    requisito="RF-08",
    objetivo="Verificar el cálculo de área de un terreno de 100×60 m recorrido con GPS ruidoso.",
    entrada="Recorrido simulado: lectura cada 2 m, ruido σ=3 m, precisión 4 m, atípicas cada 15; tolerancia automática",
    esperado="Área 6000 m² ± 5 %, perímetro 320 m ± 5 %",
)
def test_area_terreno(evidencia):
    poly = gps_polygon(_r(simulate_gps_walk(TERRENO_100x60, outlier_every=15)))
    an = analyze(poly.vertices)
    evidencia["obtenido"] = (
        f"área={an.area_m2:.1f} m², perímetro={an.perimeter_m:.1f} m, "
        f"usadas={poly.used_readings}, descartadas={poly.discarded_readings}"
    )
    assert an.area_m2 == pytest.approx(6000, rel=0.05)
    assert an.perimeter_m == pytest.approx(320, rel=0.05)


@pytest.mark.evidencia(
    id="BU-36",
    nombre="Rechazo con muy pocas lecturas válidas",
    requisito="EX-04",
    objetivo="Verificar que no se calcula un área si casi todas las lecturas son imprecisas.",
    entrada="4 lecturas, 2 con precisión 50 m",
    esperado="GeometryError",
)
def test_pocas_lecturas(evidencia):
    lecturas = [
        GpsReading(-8.13, -79.04, 3),
        GpsReading(-8.1301, -79.04, 50),
        GpsReading(-8.1301, -79.0401, 50),
        GpsReading(-8.13, -79.0401, 3),
    ]
    with pytest.raises(GeometryError) as exc:
        gps_polygon(lecturas)
    evidencia["obtenido"] = f"GeometryError: {exc.value}"
