"""Pruebas de integración: importación de mediciones de campo a la base de datos."""

import json

import pytest
from sqlalchemy import func, select

from app.models.field_data import GpsTrial, SensorCalibration, SensorReading
from app.models.reference import ReferenceMeasurement
from app.models.survey import Survey
from app.models.user import User
from app.services.field_import import parse_pg_dump
from app.services.field_importer import import_field_data
from tests.unit.test_field_import import walk_readings


def _dump() -> str:
    """Volcado pequeño con el mismo formato que el de campo (datos de prueba, sin ubicaciones reales)."""
    ref = json.dumps({"points": [{"x": 0, "y": 0}, {"x": 4, "y": 0}, {"x": 4, "y": 3}, {"x": 0, "y": 3}], "scale_n": 1.0})
    cal = json.dumps({"step_length_m": 0.5, "gyro_bias_dps": 0.0, "step_min_interval_ms": 300})
    m_cols = "id, device_id, method, place_name, reference, calibration, status, perimeter_m, area_m2, closure_error_pct, quality, result, started_at"
    lines = [f"COPY public.measurement ({m_cols}) FROM stdin;"]
    lines.append(f"1\tcel-test\tsteps\tAula prueba\t{ref}\t{cal}\tfinished\t14.0\t12.0\t1.0\tgreen\t\\N\t2026-11-03 07:00:00+00")
    lines.append("2\tcel-test\tsteps\tSin terminar\t\\N\t\\N\trecording\t\\N\t\\N\t\\N\t\\N\t\\N\t2026-11-03 07:10:00+00")
    lines.append("\\.")
    r_cols = "id, measurement_id, seq, t_ms, kind, gyro_z_dps, accel_x, accel_y, accel_z, step, pwm, lat, lon, accuracy_m"
    lines.append(f"COPY public.measurement_reading ({r_cols}) FROM stdin;")
    for i, r in enumerate(walk_readings([4, 3, 4, 3])):
        motion = r["kind"] == "motion"
        vals = [i + 1, 1, r["seq"], 1_700_000_000_000 + r["t_ms"], r["kind"],
                r["gyro_z_dps"] if motion else "\\N", 0, 0, r["accel_z"] if motion else "\\N",
                "f", "\\N", "\\N", "\\N", "\\N"]
        lines.append("\t".join(str(v) for v in vals))
    lines.append("\\.")
    fix = json.dumps([{"lat": 0.0, "lon": 0.0, "accuracy_m": 3.0}])
    fix_end = json.dumps([{"lat": 0.00027, "lon": 0.0, "accuracy_m": 3.0}])  # ≈ 30 m al norte
    lines.append("COPY public.gps_trial (id, device_id, place_name, environment, real_distance_m, start_fixes, end_fixes, result, created_at) FROM stdin;")
    lines.append(f"1\tcel-test\tCancha\topen\t30\t{fix}\t{fix_end}\t\\N\t2026-11-03 07:00:00+00")
    lines.append("\\.")
    lines.append("COPY public.sensor_calibration (id, device_id, kind, origin, params, created_at) FROM stdin;")
    lines.append('1\tcel-test\tgyro_bias\tmanual\t{"bias_dps": -0.02}\t2026-11-03 06:00:00+00')
    lines.append("\\.")
    return "\n".join(lines) + "\n"


async def _owner(db_session) -> User:
    user = User(email="campo@metrik.pe", full_name="Campo", hashed_password="x")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.evidencia(
    id="BI-29",
    nombre="Importación de mediciones de campo a la base de datos",
    requisito="Migración de datos de campo",
    objetivo="Verificar que el volcado se convierte en recorridos de MetriK con lecturas crudas, referencias, pruebas GPS y calibraciones.",
    entrada="Volcado de prueba: 1 recorrido por pasos 4 × 3 m terminado, 1 sin terminar, 1 prueba GPS de 30 m, 1 calibración",
    esperado="1 recorrido (área ≈ 12 m²), 4 referencias, las 904 lecturas crudas guardadas, prueba GPS con error < 1 m, 1 calibración",
)
async def test_importacion(db_session, evidencia):
    owner = await _owner(db_session)
    report = await import_field_data(db_session, parse_pg_dump(_dump()), owner, "Campo", "prueba")
    survey = (await db_session.execute(select(Survey))).scalar_one()
    lecturas = (await db_session.execute(select(func.count(SensorReading.id)))).scalar_one()
    refs = (await db_session.execute(select(func.count(ReferenceMeasurement.id)))).scalar_one()
    trial = (await db_session.execute(select(GpsTrial))).scalar_one()
    cals = (await db_session.execute(select(func.count(SensorCalibration.id)))).scalar_one()
    evidencia["obtenido"] = (
        f"recorridos={report.surveys_created}, área={survey.area_m2:.2f} m² (real {survey.real_area_m2}), "
        f"origen={survey.source}, referencias={refs}, lecturas={lecturas}, GPS medido={trial.measured_distance_m:.2f} m "
        f"(error {trial.error_m:+.2f} m), calibraciones={cals}, avisos={len(report.warnings)}"
    )
    assert report.surveys_created == 1 and survey.source == "importado"
    assert survey.area_m2 == pytest.approx(12.0, rel=0.03)
    assert survey.real_area_m2 == pytest.approx(12.0)
    assert refs == 4 and lecturas == len(walk_readings([4, 3, 4, 3]))
    assert abs(trial.error_m) < 1.0
    assert cals == 1
    assert any("sin terminar" in w for w in report.warnings)


@pytest.mark.evidencia(
    id="BI-30",
    nombre="Importación idempotente",
    requisito="Migración de datos de campo",
    objetivo="Verificar que importar dos veces el mismo volcado no duplica registros.",
    entrada="El mismo volcado importado dos veces",
    esperado="La segunda vez: 0 recorridos creados, 1 omitido; totales sin cambios",
)
async def test_importacion_idempotente(db_session, evidencia):
    owner = await _owner(db_session)
    tables = parse_pg_dump(_dump())
    await import_field_data(db_session, tables, owner, "Campo", "prueba")
    second = await import_field_data(db_session, tables, owner, "Campo", "prueba")
    surveys = (await db_session.execute(select(func.count(Survey.id)))).scalar_one()
    trials = (await db_session.execute(select(func.count(GpsTrial.id)))).scalar_one()
    evidencia["obtenido"] = (
        f"2.ª vez: creados={second.surveys_created}, omitidos={second.surveys_skipped}; recorridos={surveys}, pruebas GPS={trials}"
    )
    assert (second.surveys_created, second.surveys_skipped, surveys, trials) == (0, 1, 1, 1)
