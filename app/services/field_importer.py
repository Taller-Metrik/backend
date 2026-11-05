"""Carga en la base de MetriK las mediciones de campo de un volcado pg_dump (ver field_import.py).

Por cada medición del volcado:
- method=steps → recorrido INTERIOR reconstruido desde las lecturas crudas (pasos + giroscopio);
  se usan las esquinas marcadas si hay al menos 3, y la forma real del ambiente se guarda
  como medidas de referencia (para calcular el margen de error real).
- method=gps   → recorrido EXTERIOR con las lecturas GPS.
Además se importan las lecturas crudas (sensor_readings), las pruebas GPS con distancia real
(gps_trials) y las calibraciones (sensor_calibrations).

Es idempotente: cada registro lleva `source_ref` y no se vuelve a importar.
"""

import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.field_data import GpsTrial, SensorCalibration, SensorReading
from app.models.project import Project
from app.models.reference import ReferenceMeasurement
from app.models.survey import Survey, SurveyMode
from app.models.user import User
from app.schemas.project import CaptureIn, GpsPoint, SurveyCreate
from app.services import geometry
from app.services.field_import import StepParams, as_float, as_json, reconstruct_steps, reference_walls
from app.services.gps import haversine
from app.services.project_service import SurveyService

STEP_THRESHOLD_MS2 = 0.8  # calibrado con los 13 recorridos interiores reales (docs/05)


@dataclass
class ImportReport:
    surveys_created: int = 0
    surveys_skipped: int = 0
    readings: int = 0
    references: int = 0
    gps_trials: int = 0
    calibrations: int = 0
    warnings: list[str] = field(default_factory=list)


def _ts(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _mean_fix(fixes: list[dict[str, Any]]) -> tuple[float, float] | None:
    if not fixes:
        return None
    return statistics.fmean(f["lat"] for f in fixes), statistics.fmean(f["lon"] for f in fixes)


async def import_field_data(
    db: AsyncSession,
    tables: dict[str, list[dict[str, str | None]]],
    owner: User,
    project_name: str,
    prefix: str,
) -> ImportReport:
    report = ImportReport()

    project = (
        await db.execute(select(Project).where(Project.owner_id == owner.id, Project.name == project_name))
    ).scalar_one_or_none()
    if project is None:
        project = Project(owner_id=owner.id, name=project_name, description="Mediciones de campo importadas (datos reales)")
        db.add(project)
        await db.commit()
        await db.refresh(project)
    project_id = project.id

    existing = set((await db.execute(select(Survey.source_ref).where(Survey.source_ref.is_not(None)))).scalars())
    readings_by_m: dict[str, list[dict[str, Any]]] = {}
    for r in tables.get("measurement_reading", []):
        readings_by_m.setdefault(r["measurement_id"], []).append(r)
    for rows in readings_by_m.values():
        rows.sort(key=lambda r: int(r["seq"]))

    service = SurveyService(db, owner)
    for m in sorted(tables.get("measurement", []), key=lambda m: int(m["id"])):
        ref = f"{prefix}:measurement:{m['id']}"
        if ref in existing:
            report.surveys_skipped += 1
            continue
        if m.get("status") != "finished":
            report.warnings.append(f"Medición {m['id']} sin terminar (estado {m.get('status')}): no se importa")
            continue
        rows = readings_by_m.get(m["id"], [])
        place = m.get("place_name") or "Sin nombre"
        name = f"{place} #{m['id']}"
        original = as_json(m.get("result")) or {}
        meta = {
            "origen": prefix,
            "metodo_original": m.get("method"),
            "dispositivo": m.get("device_id"),
            "montaje": m.get("mount"),
            "calidad_original": m.get("quality"),
            "perimetro_original_m": as_float(m.get("perimeter_m")),
            "area_original_m2": as_float(m.get("area_m2")),
            "error_cierre_original_pct": as_float(m.get("closure_error_pct")),
            "esquinas_marcadas": original.get("corners"),
        }
        try:
            if m.get("method") == "steps":
                cal = as_json(m.get("calibration")) or {}
                params = StepParams(
                    step_length_m=float(cal.get("step_length_m") or 0.70),
                    gyro_bias_dps=float(cal.get("gyro_bias_dps") or 0.0),
                    threshold_ms2=STEP_THRESHOLD_MS2,
                    min_interval_ms=int(cal.get("step_min_interval_ms") or 300),
                )
                track = reconstruct_steps(rows, params)
                meta.update({"pasos": track.steps, "giro_total_deg": round(track.turn_total_deg, 1), "parametros_pasos": params.__dict__})
                payload = SurveyCreate(
                    name=name,
                    mode=SurveyMode.INTERIOR,
                    device_model=m.get("device_id"),
                    points=track.points,
                    corners=track.corners if len(track.corners) >= 4 else None,
                    capture=CaptureIn(odometry="steps", tracking_loss_s=0.0, duration_s=max(track.duration_s, 0.1)),
                )
            elif m.get("method") == "gps":
                gps = [
                    GpsPoint(lat=float(r["lat"]), lon=float(r["lon"]), accuracy_m=float(r["accuracy_m"] or 99), timestamp_s=int(r["t_ms"]) / 1000)
                    for r in rows
                    if r["kind"] == "gps" and r.get("lat") is not None
                ]
                payload = SurveyCreate(name=name, mode=SurveyMode.EXTERIOR, device_model=m.get("device_id"), gps_points=gps, scale_denominator=None)
            else:
                report.warnings.append(f"Medición {m['id']}: método desconocido {m.get('method')}")
                continue
            survey = await service.create(project_id, payload)
        except (geometry.GeometryError, ValueError) as exc:  # se valida antes de escribir en la BD
            report.warnings.append(f"Medición {m['id']} ({place}): no se pudo procesar — {exc}")
            continue

        survey.source = "importado"
        survey.source_ref = ref
        survey.place_name = place
        survey.measured_at = _ts(m.get("started_at"))
        survey.source_meta = meta

        # Forma real del ambiente → medidas de referencia (margen de error con datos reales)
        walls = reference_walls(as_json(m.get("reference")))
        if walls:
            reference = as_json(m.get("reference"))
            pts = [(float(p["x"]), float(p["y"])) for p in reference["points"]]
            survey.real_area_m2 = geometry.area(pts) * float(reference.get("scale_n") or 1.0) ** 2
            if len(walls) == len(survey.wall_lengths_m):
                for i, w in enumerate(walls):
                    db.add(ReferenceMeasurement(survey_id=survey.id, wall_index=i, readings_m=[w], real_length_m=w,
                                                notes="Forma real del ambiente (volcado de campo)"))
                    report.references += 1
            else:
                report.warnings.append(
                    f"Medición {m['id']}: el plano tiene {len(survey.wall_lengths_m)} muros y el real {len(walls)}; "
                    "solo se guarda el área real"
                )

        if rows:
            await db.execute(
                insert(SensorReading),
                [
                    {
                        "survey_id": survey.id, "seq": int(r["seq"]), "t_ms": int(r["t_ms"]), "kind": r["kind"],
                        "gyro_z_dps": as_float(r.get("gyro_z_dps")), "accel_x": as_float(r.get("accel_x")),
                        "accel_y": as_float(r.get("accel_y")), "accel_z": as_float(r.get("accel_z")),
                        "lat": as_float(r.get("lat")), "lon": as_float(r.get("lon")), "accuracy_m": as_float(r.get("accuracy_m")),
                    }
                    for r in rows
                ],
            )
            report.readings += len(rows)
        await db.commit()
        report.surveys_created += 1

    # Pruebas de precisión GPS con distancia real conocida
    trial_refs = set((await db.execute(select(GpsTrial.source_ref))).scalars())
    for t in tables.get("gps_trial", []):
        ref = f"{prefix}:gps_trial:{t['id']}"
        if ref in trial_refs:
            continue
        start, end = as_json(t.get("start_fixes")) or [], as_json(t.get("end_fixes")) or []
        a, b = _mean_fix(start), _mean_fix(end)
        measured = haversine(a, b) if a and b else None
        real = float(t["real_distance_m"])
        db.add(GpsTrial(
            owner_id=owner.id, device_id=t.get("device_id"), place_name=t.get("place_name"), environment=t.get("environment"),
            real_distance_m=real, start_fixes=start, end_fixes=end, measured_distance_m=measured,
            error_m=None if measured is None else measured - real, source_ref=ref, created_at=_ts(t.get("created_at")),
        ))
        report.gps_trials += 1

    # Calibraciones de sensores y ajustes de precisión
    cal_refs = set((await db.execute(select(SensorCalibration.source_ref))).scalars())
    for c in tables.get("sensor_calibration", []):
        ref = f"{prefix}:sensor_calibration:{c['id']}"
        if ref not in cal_refs:
            db.add(SensorCalibration(owner_id=owner.id, device_id=c.get("device_id"), kind=c["kind"], origin=c.get("origin"),
                                     params=as_json(c.get("params")) or {}, source_ref=ref, created_at=_ts(c.get("created_at"))))
            report.calibrations += 1
    for r in tables.get("precision_model_run", []):
        ref = f"{prefix}:precision_model_run:{r['id']}"
        if ref not in cal_refs:
            db.add(SensorCalibration(owner_id=owner.id, device_id=r.get("device_id"), kind="precision_model_run", origin="automatico",
                                     params={"measurement_ids": as_json(r.get("measurement_ids")), "result": as_json(r.get("result"))},
                                     applied=r.get("applied") == "t", source_ref=ref, created_at=_ts(r.get("created_at"))))
            report.calibrations += 1
    await db.commit()
    return report


def gps_trial_summary(trials: list[GpsTrial]) -> dict[str, float]:
    errors = [abs(t.error_m) for t in trials if t.error_m is not None]
    if not errors:
        return {}
    return {
        "n": len(errors),
        "error_medio_m": statistics.fmean(errors),
        "error_max_m": max(errors),
        "rmse_m": math.sqrt(statistics.fmean(e * e for e in errors)),
    }
