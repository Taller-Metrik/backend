"""Uso de los modelos de ML entrenados en ml/ (RF-15)."""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from app.core.config import settings
from app.models.survey import Survey, SurveyMode
from app.services.ml_features import (
    ODOMETRY_CODES,
    SURVEY_FEATURES,
    WALL_FEATURES,
    CaptureInfo,
    survey_features,
    wall_features,
)

CORRECTOR_FILE = "corrector_muros.joblib"
CLASSIFIER_FILE = "clasificador_recorrido.joblib"
RELIABILITY_THRESHOLD = 0.5


class ModelsNotAvailableError(Exception):
    """No se encontraron los archivos .joblib (ejecutar ml/entrenar_modelos.py)."""


class NotApplicableError(Exception):
    """El modelo no aplica a este tipo de recorrido."""


@lru_cache(maxsize=4)
def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ModelsNotAvailableError(f"No existe {path.name}; ejecute ml/entrenar_modelos.py")
    return joblib.load(path)


def load_models(models_dir: Path | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    base = models_dir or settings.ml_models_dir
    return _load(base / CORRECTOR_FILE), _load(base / CLASSIFIER_FILE)


@dataclass(frozen=True)
class WallCorrection:
    wall_index: int
    measured_m: float
    corrected_m: float
    correction_m: float


@dataclass(frozen=True)
class MlAnalysis:
    reliability_probability: float
    reliable: bool
    recommendation: str
    walls: list[WallCorrection]
    corrected_perimeter_m: float
    corrector_model: str
    classifier_model: str
    version: str
    correction_applied: bool = True
    correction_note: str = ""


def analyze_features(
    survey_feats: dict[str, float], wall_lengths_m: list[float], models_dir: Path | None = None
) -> MlAnalysis:
    corrector, classifier = load_models(models_dir)

    X_survey = pd.DataFrame([survey_feats])[SURVEY_FEATURES]
    probability = float(classifier["modelo"].predict_proba(X_survey)[0, 1])

    # La corrección M1 solo mejora recorridos ARCore: con mediciones de campo reales por pasos
    # empeoró el MAE (1,56 → 2,03 m, docs/06 §7), así que en ese modo no se aplica.
    apply_correction = survey_feats.get("odometry", 0.0) == ODOMETRY_CODES["arcore"]
    if apply_correction:
        X_walls = pd.DataFrame(wall_features(survey_feats, wall_lengths_m))[WALL_FEATURES]
        predicted_error = corrector["modelo"].predict(X_walls)
    else:
        predicted_error = [0.0] * len(wall_lengths_m)
    walls = [
        WallCorrection(wall_index=i, measured_m=m, corrected_m=float(m - e), correction_m=float(-e))
        for i, (m, e) in enumerate(zip(wall_lengths_m, predicted_error, strict=True))
    ]
    reliable = probability >= RELIABILITY_THRESHOLD
    return MlAnalysis(
        reliability_probability=probability,
        reliable=reliable,
        recommendation=(
            "Recorrido confiable: puede usar las medidas"
            if reliable
            else "Recorrido poco confiable: repita el recorrido más despacio y cerca de las paredes"
        ),
        walls=walls,
        corrected_perimeter_m=sum(w.corrected_m for w in walls),
        corrector_model=corrector["info"]["modelo_elegido"],
        classifier_model=classifier["info"]["modelo_elegido"],
        version=corrector["info"].get("version", ""),
        correction_applied=apply_correction,
        correction_note=(
            "Corrección aplicada (modelo entrenado para el odómetro ARCore)"
            if apply_correction
            else "Sin corrección: en datos reales por pasos el modelo no reduce el error"
        ),
    )


def analyze_survey(survey: Survey, models_dir: Path | None = None) -> MlAnalysis:
    if survey.mode != SurveyMode.INTERIOR:
        raise NotApplicableError("Los modelos se entrenaron para recorridos interiores (odómetro)")
    capture = CaptureInfo(**survey.capture) if survey.capture else CaptureInfo()
    feats = survey_features(
        wall_lengths_m=list(survey.wall_lengths_m),
        concave_count=survey.concave_count,
        closure_error_m=survey.closure_error_m,
        snapped_edges=survey.snapped_edges,
        total_edges=survey.total_edges,
        is_simple=survey.is_simple,
        capture=capture,
    )
    return analyze_features(feats, list(survey.wall_lengths_m), models_dir)


def models_info(models_dir: Path | None = None) -> dict[str, Any]:
    corrector, classifier = load_models(models_dir)
    keep = ("tarea", "objetivo", "modelo_elegido", "variables", "prueba", "version")
    return {
        "corrector_muros": {k: corrector["info"].get(k) for k in keep},
        "clasificador_recorrido": {k: classifier["info"].get(k) for k in keep},
    }
