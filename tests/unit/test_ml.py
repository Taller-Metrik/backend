"""Pruebas unitarias de variables y uso de los modelos de ML (RF-15)."""

import pytest

from app.services import ml_service
from app.services.ml_features import SURVEY_FEATURES, WALL_FEATURES, CaptureInfo, survey_features, wall_features

BASE = dict(concave_count=0, closure_error_m=0.12, snapped_edges=4, total_edges=4, is_simple=True)


@pytest.mark.evidencia(
    id="BU-49",
    nombre="Variables del recorrido para el clasificador",
    requisito="RF-15",
    objetivo="Verificar el cálculo de las variables del recorrido a partir del plano y la captura.",
    entrada="Muros [5, 4, 5, 4] m, cierre 0.12 m, captura ARCore de 36 s con 1.5 s sin seguimiento",
    esperado="perímetro 18, closure_ratio 0.00667, velocidad 0.5 m/s, odometry=0, todas las columnas del modelo",
)
def test_variables_recorrido(evidencia):
    f = survey_features(
        wall_lengths_m=[5, 4, 5, 4], capture=CaptureInfo("arcore", 1.5, 36.0), **BASE
    )
    evidencia["obtenido"] = {k: round(v, 5) for k, v in f.items()}
    assert set(SURVEY_FEATURES) <= set(f)
    assert f["perimeter_m"] == 18 and f["walking_speed_mps"] == pytest.approx(0.5)
    assert f["closure_ratio"] == pytest.approx(0.12 / 18) and f["odometry"] == 0


@pytest.mark.evidencia(
    id="BU-50",
    nombre="Variables por muro con distancia acumulada",
    requisito="RF-15",
    objetivo="Verificar que cada muro lleva su posición y la distancia acumulada (la deriva crece con ella).",
    entrada="Muros [5, 4, 5, 4] m",
    esperado="distancias acumuladas [5, 9, 14, 18] y posiciones relativas hasta 1.0",
)
def test_variables_muro(evidencia):
    f = survey_features(wall_lengths_m=[5, 4, 5, 4], capture=CaptureInfo(), **BASE)
    rows = wall_features(f, [5, 4, 5, 4])
    acumuladas = [r["cumulative_distance_m"] for r in rows]
    evidencia["obtenido"] = f"acumuladas={acumuladas}, relativas={[round(r['relative_position'], 3) for r in rows]}"
    assert acumuladas == [5, 9, 14, 18]
    assert rows[-1]["relative_position"] == pytest.approx(1.0)
    assert all(set(WALL_FEATURES) <= set(r) for r in rows)


@pytest.mark.evidencia(
    id="BU-51",
    nombre="Corrección del sesgo sistemático por el modelo M1",
    requisito="RF-15",
    objetivo="Verificar que el modelo corrige el acortamiento sistemático (la persona camina separada de la pared).",
    entrada="Recorrido ARCore confiable de 4 muros medidos [4.94, 3.94, 4.94, 3.94] m",
    esperado="Todas las longitudes corregidas son mayores que las medidas (corrección positiva de pocos cm)",
)
def test_correccion_modelo(evidencia):
    walls = [4.94, 3.94, 4.94, 3.94]
    f = survey_features(wall_lengths_m=walls, capture=CaptureInfo("arcore", 0.0, 22.0), **BASE)
    r = ml_service.analyze_features(f, walls)
    evidencia["obtenido"] = f"corregidas={[round(w.corrected_m, 3) for w in r.walls]}, modelo={r.corrector_model}"
    assert all(0 < w.correction_m < 0.25 for w in r.walls)


@pytest.mark.evidencia(
    id="BU-52",
    nombre="Clasificador distingue recorrido bueno de uno malo",
    requisito="RF-15",
    objetivo="Verificar que M2 da mayor probabilidad de confiable a un recorrido limpio que a uno con deriva.",
    entrada="Bueno: ARCore, cierre 5 cm, sin pérdidas. Malo: pasos, cierre 1.2 m, 6 s sin seguimiento, 3 lados no ortogonales",
    esperado="P(bueno) ≥ 0.5 > P(malo)",
)
def test_clasificador(evidencia):
    walls = [5, 4, 5, 4]
    bueno = survey_features(
        wall_lengths_m=walls, concave_count=0, closure_error_m=0.05, snapped_edges=4, total_edges=4,
        is_simple=True, capture=CaptureInfo("arcore", 0.0, 20.0),
    )
    malo = survey_features(
        wall_lengths_m=walls, concave_count=0, closure_error_m=1.2, snapped_edges=4, total_edges=7,
        is_simple=True, capture=CaptureInfo("steps", 6.0, 20.0),
    )
    p_bueno = ml_service.analyze_features(bueno, walls).reliability_probability
    p_malo = ml_service.analyze_features(malo, walls).reliability_probability
    evidencia["obtenido"] = f"P(bueno)={p_bueno:.3f}, P(malo)={p_malo:.3f}"
    assert p_bueno >= 0.5 > p_malo


@pytest.mark.evidencia(
    id="BU-53",
    nombre="Error claro si faltan los modelos",
    requisito="RF-15",
    objetivo="Verificar el mensaje cuando no se han entrenado los modelos.",
    entrada="Carpeta de modelos vacía",
    esperado="ModelsNotAvailableError indicando ejecutar ml/entrenar_modelos.py",
)
def test_modelos_faltantes(tmp_path, evidencia):
    with pytest.raises(ml_service.ModelsNotAvailableError) as exc:
        ml_service.load_models(tmp_path)
    evidencia["obtenido"] = f"ModelsNotAvailableError: {exc.value}"
    assert "entrenar_modelos.py" in str(exc.value)


@pytest.mark.evidencia(
    id="BU-57",
    nombre="Sin corrección M1 en recorridos por pasos",
    requisito="RF-15",
    objetivo="Verificar que la corrección solo se aplica al odómetro ARCore (en datos reales por pasos empeoraba el error).",
    entrada="Mismos muros con captura 'steps' y con captura 'arcore'",
    esperado="steps: medidas sin cambio y nota explicativa; arcore: corrección aplicada",
)
def test_sin_correccion_en_pasos(evidencia):
    walls = [4.94, 3.94, 4.94, 3.94]
    pasos = ml_service.analyze_features(survey_features(wall_lengths_m=walls, capture=CaptureInfo("steps", 0.0, 22.0), **BASE), walls)
    arcore = ml_service.analyze_features(survey_features(wall_lengths_m=walls, capture=CaptureInfo("arcore", 0.0, 22.0), **BASE), walls)
    evidencia["obtenido"] = (
        f"steps: aplicada={pasos.correction_applied}, corregidas={[w.corrected_m for w in pasos.walls]} ('{pasos.correction_note}'); "
        f"arcore: aplicada={arcore.correction_applied}"
    )
    assert pasos.correction_applied is False
    assert [w.corrected_m for w in pasos.walls] == walls
    assert arcore.correction_applied is True
