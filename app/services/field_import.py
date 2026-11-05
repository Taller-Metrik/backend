"""Importación de mediciones de campo desde un volcado de PostgreSQL (pg_dump, formato COPY).

El archivo se interpreta como texto: NO se ejecuta el SQL. Se leen los bloques
`COPY public.<tabla> (...) FROM stdin; ... \\.` y cada fila se convierte en un diccionario.

Luego las lecturas crudas de sensores se procesan con los mismos algoritmos de MetriK:
- Recorridos por pasos: detector de pasos (acelerómetro) + rumbo integrando el giroscopio.
- Recorridos GPS: lecturas lat/lon con su precisión.
"""

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.services.geometry import Point

_COPY = re.compile(r"^COPY\s+(?:public\.)?(\w+)\s+\(([^)]*)\)\s+FROM\s+stdin;\s*$")
_ESCAPES = {"t": "\t", "n": "\n", "r": "\r", "\\": "\\", "b": "\b", "f": "\f", "v": "\v"}


def _unescape(value: str) -> str | None:
    if value == r"\N":
        return None
    return re.sub(r"\\(.)", lambda m: _ESCAPES.get(m.group(1), m.group(1)), value)


def parse_pg_dump(text: str) -> dict[str, list[dict[str, str | None]]]:
    """Devuelve {tabla: [fila, ...]} con los valores como texto (None para NULL)."""
    tables: dict[str, list[dict[str, str | None]]] = {}
    current: str | None = None
    columns: list[str] = []
    for line in text.splitlines():
        if current is None:
            m = _COPY.match(line)
            if m:
                current = m.group(1)
                columns = [c.strip().strip('"') for c in m.group(2).split(",")]
                tables.setdefault(current, [])
            continue
        if line == r"\.":
            current = None
            continue
        values = line.split("\t")
        if len(values) != len(columns):
            raise ValueError(f"Fila con {len(values)} columnas en {current}; se esperaban {len(columns)}")
        tables[current].append({c: _unescape(v) for c, v in zip(columns, values, strict=True)})
    return tables


def load_dump(path: str | Path) -> dict[str, list[dict[str, str | None]]]:
    return parse_pg_dump(Path(path).read_text(encoding="utf-8"))


def as_json(value: str | None) -> Any:
    return None if value in (None, "", "null") else json.loads(value)


def as_float(value: str | None) -> float | None:
    return None if value is None else float(value)


# ---------------------------------------------------------------- reconstrucción por pasos


@dataclass(frozen=True)
class StepParams:
    step_length_m: float = 0.70
    gyro_bias_dps: float = 0.0
    threshold_ms2: float = 0.8
    min_interval_ms: int = 300
    alpha: float = 0.25


@dataclass
class StepTrack:
    points: list[Point]
    corners: list[Point]
    steps: int
    duration_s: float
    turn_total_deg: float
    corner_times_ms: list[int] = field(default_factory=list)


GRAVITY = 9.80665


def reconstruct_steps(readings: list[dict[str, Any]], params: StepParams) -> StepTrack:
    """Odometría por pasos (PDR) sobre lecturas reales ordenadas por `seq`.

    - Paso: pico del módulo del acelerómetro filtrado (EMA) sobre la gravedad + umbral,
      con un intervalo mínimo entre pasos (mismo detector que la app).
    - Rumbo: integral de (giro_z − sesgo calibrado) en el tiempo.
    - Cada esquina marcada por el usuario se registra en la posición del momento.
    El recorrido empieza en una esquina, por eso el origen es la primera esquina.
    """
    filtered: float | None = None
    above = False
    last_step = -(10**18)
    heading = 0.0
    turn = 0.0
    prev_t: int | None = None
    x = y = 0.0
    points: list[Point] = [(0.0, 0.0)]
    corners: list[Point] = [(0.0, 0.0)]
    corner_times: list[int] = []
    steps = 0
    t0: int | None = None
    t_end = 0
    for r in readings:
        t = int(r["t_ms"])
        t0 = t if t0 is None else t0
        t_end = t
        kind = r["kind"]
        if kind == "corner":
            corners.append((x, y))
            corner_times.append(t)
            continue
        if kind != "motion" or r.get("gyro_z_dps") is None:
            continue
        gz = float(r["gyro_z_dps"])
        if prev_t is not None:
            d = (gz - params.gyro_bias_dps) * (t - prev_t) / 1000.0
            heading += math.radians(d)
            turn += d
        prev_t = t
        ax, ay, az = (float(r[k]) for k in ("accel_x", "accel_y", "accel_z"))
        magnitude = math.sqrt(ax * ax + ay * ay + az * az)
        filtered = magnitude if filtered is None else filtered + params.alpha * (magnitude - filtered)
        is_above = filtered - GRAVITY > params.threshold_ms2
        if is_above and not above and t - last_step >= params.min_interval_ms:
            steps += 1
            last_step = t
            x += params.step_length_m * math.cos(heading)
            y += params.step_length_m * math.sin(heading)
            points.append((x, y))
        above = is_above
    return StepTrack(
        points=points,
        corners=corners,
        steps=steps,
        duration_s=(t_end - t0) / 1000.0 if t0 is not None else 0.0,
        turn_total_deg=turn,
        corner_times_ms=corner_times,
    )


def reference_walls(reference: dict[str, Any] | None) -> list[float]:
    """Longitudes reales de los muros a partir del polígono de referencia del dump."""
    if not reference or not reference.get("points"):
        return []
    pts = [(float(p["x"]), float(p["y"])) for p in reference["points"]]
    scale = float(reference.get("scale_n") or 1.0)
    return [math.dist(pts[i], pts[(i + 1) % len(pts)]) * scale for i in range(len(pts))]
