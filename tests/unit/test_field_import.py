"""Pruebas unitarias del lector de volcados y de la reconstrucción por pasos (importación de campo)."""

import json
import math

import pytest

from app.services.field_import import StepParams, parse_pg_dump, reconstruct_steps, reference_walls

DUMP = (
    "--\n-- PostgreSQL database dump\n--\nSET client_encoding = 'UTF8';\n\n"
    "COPY public.measurement (id, method, place_name, reference) FROM stdin;\n"
    '1\tsteps\tAula\t{"points": [{"x": 0.0, "y": 0.0}, {"x": 4.0, "y": 0.0}, {"x": 4.0, "y": 3.0}, {"x": 0.0, "y": 3.0}], "scale_n": 1.0}\n'
    "2\tgps\tCalle con\\ttab\t\\N\n"
    "\\.\n\nSELECT pg_catalog.setval('public.measurement_id_seq', 2, true);\n"
)


def walk_readings(sides: list[float], step_m: float = 0.5, hz: int = 50) -> list[dict]:
    """Lecturas crudas de una caminata rectangular: pasos en el acelerómetro y giros de 90° en el giroscopio."""
    readings: list[dict] = []
    t = 0
    seq = 0

    def add(kind: str, gz: float = 0.0, az: float = 9.80665) -> None:
        nonlocal seq
        readings.append({"seq": seq, "t_ms": t, "kind": kind, "gyro_z_dps": gz, "accel_x": 0.0, "accel_y": 0.0, "accel_z": az})
        seq += 1

    for side in sides:
        for _ in range(round(side / step_m)):  # un paso cada 500 ms: pico de 2.5 m/s² durante 100 ms
            for k in range(25):
                add("motion", az=9.80665 + (2.5 if 5 <= k < 10 else 0.0))
                t += 1000 // hz
        add("corner")
        for _ in range(50):  # giro de 90° en 1 s
            add("motion", gz=90.0)
            t += 1000 // hz
    return readings


@pytest.mark.evidencia(
    id="BU-54",
    nombre="Lectura de un volcado pg_dump sin ejecutar SQL",
    requisito="Importación de datos de campo",
    objetivo="Verificar que se leen los bloques COPY con NULL y escapes, ignorando el resto del SQL.",
    entrada="Volcado con 2 filas (una con \\N y una con \\t escapado) y sentencias SET/SELECT",
    esperado="1 tabla, 2 filas; NULL → None; '\\t' → tabulación real",
)
def test_parse_pg_dump(evidencia):
    tables = parse_pg_dump(DUMP)
    rows = tables["measurement"]
    evidencia["obtenido"] = f"tablas={list(tables)}, filas={len(rows)}, lugar2={rows[1]['place_name']!r}, ref2={rows[1]['reference']}"
    assert list(tables) == ["measurement"] and len(rows) == 2
    assert rows[1]["reference"] is None
    assert rows[1]["place_name"] == "Calle con\ttab"


@pytest.mark.evidencia(
    id="BU-55",
    nombre="Medidas reales desde el polígono de referencia",
    requisito="RF-13",
    entrada="Referencia 4 × 3 m del volcado",
    esperado="Muros [4, 3, 4, 3] m",
)
def test_reference_walls(evidencia):
    walls = reference_walls(json.loads(parse_pg_dump(DUMP)["measurement"][0]["reference"]))
    evidencia["obtenido"] = f"{walls}"
    assert walls == pytest.approx([4, 3, 4, 3])


@pytest.mark.evidencia(
    id="BU-56",
    nombre="Reconstrucción de un recorrido por pasos con giroscopio",
    requisito="RF-01, RF-02 (odómetro por pasos)",
    objetivo="Verificar la odometría por pasos sobre lecturas crudas: pasos del acelerómetro, rumbo del giroscopio y esquinas.",
    entrada="Caminata 4 × 3 m con pasos de 0.5 m y giros de 90° (lecturas a 50 Hz)",
    esperado="28 pasos (14 m), 4 esquinas, giro total 360°, regreso al origen (< 5 cm)",
)
def test_reconstruct_steps(evidencia):
    track = reconstruct_steps(walk_readings([4, 3, 4, 3]), StepParams(step_length_m=0.5, threshold_ms2=0.8))
    end = track.points[-1]
    evidencia["obtenido"] = (
        f"pasos={track.steps}, esquinas={len(track.corners) - 1}, giro={track.turn_total_deg:.1f}°, "
        f"fin=({end[0]:.3f}, {end[1]:.3f})"
    )
    assert track.steps == 28
    assert track.duration_s > 0
    assert len(track.corners) == 5
    assert track.turn_total_deg == pytest.approx(360, abs=1)
    assert math.hypot(*end) < 0.05
