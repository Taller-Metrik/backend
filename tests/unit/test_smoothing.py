"""Pruebas unitarias del suavizado de trazos (RF-02, RF-05)."""

import pytest

from app.services.geometry import analyze
from app.services.smoothing import dominant_orientation, rdp, smooth_track, snap_turn_angle
from tests.helpers import AMBIENTE_L, AMBIENTE_U, RECTANGULO_5x4, simulate_walk


@pytest.mark.evidencia(
    id="BU-14",
    nombre="Ajuste de giro del giroscopio a 90°",
    requisito="RF-02",
    objetivo="Verificar que giros cercanos a 90° se ajustan y los lejanos se conservan.",
    entrada="87°, 93.5°, -88°, 178°, 60° con tolerancia 15°",
    esperado="90°, 90°, -90°, 180°, 60°",
)
def test_ajuste_giro(evidencia):
    entradas = [87, 93.5, -88, 178, 60]
    salidas = [snap_turn_angle(a, 15) for a in entradas]
    evidencia["obtenido"] = str(salidas)
    assert salidas == [90, 90, -90, 180, 60]


@pytest.mark.evidencia(
    id="BU-15",
    nombre="Simplificación Ramer-Douglas-Peucker",
    requisito="RF-05",
    objetivo="Verificar que RDP elimina puntos casi colineales y conserva las esquinas.",
    entrada="Línea de (0,0) a (10,0) con 101 puntos y desvío de 2 cm, luego esquina a (10,5)",
    esperado="3 puntos: (0,0), (10,0), (10,5)",
)
def test_rdp(evidencia):
    pts = [(i / 10, 0.02 if i % 2 else 0.0) for i in range(101)] + [(10, 5)]
    pts[100] = (10.0, 0.0)
    out = rdp(pts, epsilon=0.1)
    evidencia["obtenido"] = f"{len(out)} puntos: {out}"
    assert out == [(0, 0.0), (10.0, 0.0), (10, 5)]


@pytest.mark.evidencia(
    id="BU-16",
    nombre="Orientación dominante de un ambiente rotado",
    requisito="RF-05",
    objetivo="Verificar que se detecta la rotación del ambiente respecto al norte del celular.",
    entrada="Lados de un rectángulo rotado 20°",
    esperado="20° ± 0.01",
)
def test_orientacion_dominante(evidencia):
    import math

    a = math.radians(20)
    lados = [(5 * math.cos(a), 5 * math.sin(a)), (-4 * math.sin(a), 4 * math.cos(a))]
    resultado = math.degrees(dominant_orientation(lados))
    evidencia["obtenido"] = f"{resultado:.4f}°"
    assert resultado == pytest.approx(20.0, abs=0.01)


@pytest.mark.evidencia(
    id="BU-17",
    nombre="Suavizado de un recorrido rectangular con ruido",
    requisito="RF-05",
    objetivo="Verificar que un trazo ruidoso de un aula 5×4 m queda como rectángulo con ángulos de 90°.",
    entrada="Trazo simulado: paso 5 cm, ruido σ=3 cm, ambiente rotado 20°",
    esperado="4 vértices, ángulos de 90°, área 20 m² ± 2 %",
)
def test_suavizado_rectangulo(evidencia):
    r = smooth_track(simulate_walk(RECTANGULO_5x4))
    an = analyze(r.vertices)
    evidencia["obtenido"] = (
        f"{len(r.vertices)} vértices, área={an.area_m2:.3f} m², "
        f"muros={[round(w, 2) for w in an.wall_lengths_m]}, ángulos={[round(x) for x in an.interior_angles_deg]}"
    )
    assert len(r.vertices) == 4
    assert all(a == pytest.approx(90, abs=0.01) for a in an.interior_angles_deg)
    assert an.area_m2 == pytest.approx(20.0, rel=0.02)


@pytest.mark.evidencia(
    id="BU-18",
    nombre="Suavizado de ambientes cóncavos (L y U)",
    requisito="RF-05",
    objetivo="Verificar que el suavizado conserva los vértices cóncavos.",
    entrada="Trazos simulados de ambientes en L y en U (24 m² cada uno) con ruido σ=3 cm",
    esperado="L: 6 vértices con un ángulo de 270°; U: 8 vértices con dos de 270°; área 24 m² ± 2 %",
)
def test_suavizado_concavos(evidencia):
    rl = analyze(smooth_track(simulate_walk(AMBIENTE_L, seed=2)).vertices)
    ru = analyze(smooth_track(simulate_walk(AMBIENTE_U, seed=3)).vertices)
    evidencia["obtenido"] = (
        f"L: {len(rl.vertices)} vértices, área={rl.area_m2:.3f}, cóncavos={len(rl.concave_vertices)} | "
        f"U: {len(ru.vertices)} vértices, área={ru.area_m2:.3f}, cóncavos={len(ru.concave_vertices)}"
    )
    assert (len(rl.vertices), len(rl.concave_vertices)) == (6, 1)
    assert (len(ru.vertices), len(ru.concave_vertices)) == (8, 2)
    assert rl.area_m2 == pytest.approx(24.0, rel=0.02)
    assert ru.area_m2 == pytest.approx(24.0, rel=0.02)


@pytest.mark.evidencia(
    id="BU-19",
    nombre="Recorrido que no se cierra (cierre automático)",
    requisito="EX-01",
    objetivo="Verificar que un recorrido que termina lejos del inicio se marca como no cerrado y se cierra automáticamente.",
    entrada="Esquinas (0,0), (5,0), (5,4), (0,4), (0,2) — termina a 2 m del inicio",
    esperado="closed=False y polígono válido de 4 vértices",
)
def test_recorrido_no_cerrado(evidencia):
    r = smooth_track([], corners=[(0, 0), (5, 0), (5, 4), (0, 4), (0, 2)])
    evidencia["obtenido"] = f"closed={r.closed}, vértices={r.vertices}"
    assert r.closed is False
    assert len(r.vertices) == 4
    assert analyze(r.vertices).area_m2 == pytest.approx(20.0)


@pytest.mark.evidencia(
    id="BU-20",
    nombre="Repartición del error de cierre",
    requisito="RF-05",
    objetivo="Verificar que el error de cierre de esquinas marcadas se reparte y el polígono queda cerrado y ortogonal.",
    entrada="Esquinas (0,0), (5.05,0), (5.05,4.02), (0.03,3.98), (0.04,0.05)",
    esperado="Error de cierre ≈ 0.064 m, 4 ángulos de 90°, muros opuestos iguales",
)
def test_reparticion_error_cierre(evidencia):
    r = smooth_track([], corners=[(0, 0), (5.05, 0), (5.05, 4.02), (0.03, 3.98), (0.04, 0.05)])
    an = analyze(r.vertices)
    w = an.wall_lengths_m
    evidencia["obtenido"] = f"cierre={r.closure_error_m:.3f} m, muros={[round(x, 3) for x in w]}"
    assert r.closed is True
    assert r.closure_error_m == pytest.approx(0.064, abs=0.002)
    assert all(a == pytest.approx(90, abs=0.01) for a in an.interior_angles_deg)
    assert w[0] == pytest.approx(w[2], abs=1e-6) and w[1] == pytest.approx(w[3], abs=1e-6)
