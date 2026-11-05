"""Importa mediciones de campo (volcado pg_dump) a la base de MetriK.

Uso (desde backend/, con DATABASE_URL en .env):
    .venv/Scripts/python scripts/importar_mediciones.py --archivo ruta/mediciones_tatiana.sql \\
        --email tatiana@metrik.pe --nombre "Tatiana" --password "<clave para la cuenta nueva>"

- Si la cuenta ya existe, los datos se agregan a ella (no hace falta --password).
- Es idempotente: volver a ejecutarlo no duplica registros.
- El archivo se lee como texto; NO se ejecuta el SQL del volcado.
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

import app.models  # noqa: E402,F401
from app.core.database import SessionLocal, engine  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.field_data import GpsTrial  # noqa: E402
from app.models.project import Project  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.field_import import load_dump  # noqa: E402
from app.services.field_importer import gps_trial_summary, import_field_data  # noqa: E402
from app.services.validation_service import ValidationService  # noqa: E402


async def main(args: argparse.Namespace) -> int:
    tables = load_dump(args.archivo)
    print("Tablas leídas: " + ", ".join(f"{k} ({len(v)})" for k, v in tables.items()))
    async with SessionLocal() as db:
        owner = (await db.execute(select(User).where(User.email == args.email.lower()))).scalar_one_or_none()
        if owner is None:
            if not args.password or len(args.password) < 8:
                print("La cuenta no existe: indica --password (mínimo 8 caracteres) para crearla.")
                return 2
            owner = User(email=args.email.lower(), full_name=args.nombre, hashed_password=hash_password(args.password))
            db.add(owner)
            await db.commit()
            await db.refresh(owner)
            print(f"Cuenta creada: {owner.email}")

        report = await import_field_data(db, tables, owner, args.proyecto, args.prefijo)
        print(
            f"\nRecorridos creados: {report.surveys_created} (ya existían: {report.surveys_skipped})\n"
            f"Lecturas crudas: {report.readings} · Referencias reales: {report.references} · "
            f"Pruebas GPS: {report.gps_trials} · Calibraciones: {report.calibrations}"
        )
        for w in report.warnings:
            print(f"  aviso: {w}")

        trials = list((await db.execute(select(GpsTrial).where(GpsTrial.owner_id == owner.id))).scalars())
        if s := gps_trial_summary(trials):
            print(
                f"\nGPS (distancia real conocida): n={s['n']}, error medio {s['error_medio_m']:.2f} m, "
                f"RMSE {s['rmse_m']:.2f} m, máximo {s['error_max_m']:.2f} m"
            )

        project = (
            await db.execute(select(Project).where(Project.owner_id == owner.id, Project.name == args.proyecto))
        ).scalar_one()
        try:
            validated, rep = await ValidationService(db, owner).project_report(project.id)
            print(
                f"Margen de error real (muros con forma real conocida): {validated} recorridos, {rep.n} muros, "
                f"MAE {rep.mae_m:.2f} m, error relativo medio {rep.mean_rel_error_pct:.1f} %"
            )
        except ValueError as exc:
            print(f"Margen de error: {exc}")
    await engine.dispose()
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--archivo", required=True)
    p.add_argument("--email", required=True)
    p.add_argument("--nombre", default="Tatiana")
    p.add_argument("--password", default=None)
    p.add_argument("--proyecto", default="Mediciones de campo")
    p.add_argument("--prefijo", default="tatiana")
    sys.exit(asyncio.run(main(p.parse_args())))
