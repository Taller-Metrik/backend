"""Variables (features) de los modelos de ML. Fuente única para entrenamiento y predicción.

Ver docs/06-dataset-ml.md, sección 4.
"""

from dataclasses import dataclass

ODOMETRY_CODES = {"arcore": 0, "steps": 1}

WALL_FEATURES: list[str] = [
    "measured_length_m",
    "wall_index",
    "cumulative_distance_m",
    "relative_position",
    "n_vertices",
    "concave_count",
    "perimeter_m",
    "closure_error_m",
    "closure_ratio",
    "odometry",
    "tracking_loss_s",
    "walking_speed_mps",
]

SURVEY_FEATURES: list[str] = [
    "n_vertices",
    "concave_count",
    "perimeter_m",
    "closure_error_m",
    "closure_ratio",
    "snapped_ratio",
    "odometry",
    "tracking_loss_s",
    "walking_speed_mps",
    "is_simple",
]


@dataclass(frozen=True)
class CaptureInfo:
    """Metadatos de captura enviados por la app."""

    odometry: str = "arcore"  # "arcore" | "steps"
    tracking_loss_s: float = 0.0
    duration_s: float | None = None


def survey_features(
    *,
    wall_lengths_m: list[float],
    concave_count: int,
    closure_error_m: float,
    snapped_edges: int,
    total_edges: int,
    is_simple: bool,
    capture: CaptureInfo,
) -> dict[str, float]:
    perimeter = sum(wall_lengths_m)
    speed = perimeter / capture.duration_s if capture.duration_s else 1.0
    return {
        "n_vertices": float(len(wall_lengths_m)),
        "concave_count": float(concave_count),
        "perimeter_m": perimeter,
        "closure_error_m": closure_error_m,
        "closure_ratio": closure_error_m / perimeter if perimeter else 0.0,
        "snapped_ratio": snapped_edges / total_edges if total_edges else 1.0,
        "odometry": float(ODOMETRY_CODES.get(capture.odometry, 0)),
        "tracking_loss_s": capture.tracking_loss_s,
        "walking_speed_mps": speed,
        "is_simple": 1.0 if is_simple else 0.0,
    }


def wall_features(survey: dict[str, float], wall_lengths_m: list[float]) -> list[dict[str, float]]:
    """Una fila por muro, combinando datos del muro con los del recorrido."""
    rows: list[dict[str, float]] = []
    cumulative = 0.0
    perimeter = survey["perimeter_m"] or 1.0
    for i, length in enumerate(wall_lengths_m):
        cumulative += length
        rows.append(
            {
                "measured_length_m": length,
                "wall_index": float(i),
                "cumulative_distance_m": cumulative,
                "relative_position": cumulative / perimeter,
                **{k: survey[k] for k in WALL_FEATURES if k in survey},
            }
        )
    return rows
