"""Pruebas de integración: medidas reales y reportes de error con base de datos."""

import pytest
from sqlalchemy import func, select

from app.models.reference import ReferenceMeasurement

# Aula medida por la app con pequeños errores: muros 5.05, 4.02, 5.05, 4.02 (rectángulo)
APP_CORNERS = [(0, 0), (5.05, 0), (5.05, 4.02), (0, 4.02), (0, 0)]


async def _survey(auth_client, project, api, name="Aula 201") -> dict:
    resp = await auth_client.post(f"{api}/projects/{project['id']}/surveys", json={"name": name, "corners": APP_CORNERS})
    assert resp.status_code == 201, resp.text
    return resp.json()


WINCHA = {
    "walls": [
        {"wall_index": 0, "readings_m": [5.00, 5.002]},
        {"wall_index": 1, "readings_m": [4.00, 4.001]},
        {"wall_index": 2, "readings_m": [5.00, 5.03]},
        {"wall_index": 3, "readings_m": [3.998, 4.00]},
    ],
    "real_area_m2": 20.0,
}


@pytest.mark.evidencia(
    id="BI-22",
    nombre="Registrar medidas de wincha y obtener el error",
    requisito="RF-13, RF-14",
    objetivo="Verificar que PUT /surveys/{id}/references guarda las lecturas y calcula el margen de error.",
    entrada="Aula medida por la app (5.05 × 4.02 m) y lecturas de wincha de los 4 muros; área real 20 m²",
    esperado="HTTP 200, 4 registros en BD, error rel. medio < 3 %, aviso en el muro 3 (lecturas difieren 3 cm)",
)
async def test_registrar_referencias(auth_client, project, db_session, api, evidencia):
    survey = await _survey(auth_client, project, api)
    resp = await auth_client.put(f"{api}/surveys/{survey['id']}/references", json=WINCHA)
    body = resp.json()
    en_bd = (await db_session.execute(select(func.count(ReferenceMeasurement.id)))).scalar_one()
    evidencia["obtenido"] = (
        f"HTTP {resp.status_code}, BD={en_bd}, MAE={body['report']['mae_m']:.4f} m, "
        f"rel={body['report']['mean_rel_error_pct']:.2f} %, área={body['report']['area_error_pct']:.2f} %, "
        f"avisos={body['warnings']}"
    )
    assert resp.status_code == 200 and en_bd == 4
    assert body["report"]["mean_rel_error_pct"] < 3
    assert len(body["warnings"]) == 1 and "Muro 3" in body["warnings"][0]


@pytest.mark.evidencia(
    id="BI-23",
    nombre="Reemplazo de medidas reales",
    requisito="RF-13",
    objetivo="Verificar que volver a enviar las medidas reemplaza las anteriores (no duplica).",
    entrada="Dos PUT consecutivos: 4 muros y luego 2 muros",
    esperado="2 registros en BD tras el segundo envío",
)
async def test_reemplazo_referencias(auth_client, project, db_session, api, evidencia):
    survey = await _survey(auth_client, project, api)
    await auth_client.put(f"{api}/surveys/{survey['id']}/references", json=WINCHA)
    await auth_client.put(
        f"{api}/surveys/{survey['id']}/references",
        json={"walls": [{"wall_index": 0, "readings_m": [5.0]}, {"wall_index": 1, "readings_m": [4.0]}]},
    )
    en_bd = (await db_session.execute(select(func.count(ReferenceMeasurement.id)))).scalar_one()
    evidencia["obtenido"] = f"registros en BD={en_bd}"
    assert en_bd == 2


@pytest.mark.evidencia(
    id="BI-24",
    nombre="Muro inexistente en las medidas reales",
    requisito="RF-13",
    objetivo="Verificar la validación del índice de muro contra el recorrido guardado.",
    entrada="wall_index=7 en un recorrido de 4 muros",
    esperado="HTTP 422 con mensaje de índices válidos",
)
async def test_muro_inexistente(auth_client, project, api, evidencia):
    survey = await _survey(auth_client, project, api)
    resp = await auth_client.put(
        f"{api}/surveys/{survey['id']}/references", json={"walls": [{"wall_index": 7, "readings_m": [3.0]}]}
    )
    evidencia["obtenido"] = f"HTTP {resp.status_code}: {resp.json()['detail']}"
    assert resp.status_code == 422


@pytest.mark.evidencia(
    id="BI-25",
    nombre="Planilla CSV del proyecto",
    requisito="RF-14",
    objetivo="Verificar la descarga del CSV con todas las comparaciones del proyecto.",
    entrada="Proyecto con 2 recorridos validados (4 muros cada uno)",
    esperado="HTTP 200, text/csv, 1 encabezado + 8 filas",
)
async def test_csv_proyecto(auth_client, project, api, evidencia):
    for nombre in ("Aula 201", "Aula 202"):
        s = await _survey(auth_client, project, api, nombre)
        await auth_client.put(f"{api}/surveys/{s['id']}/references", json=WINCHA)
    resp = await auth_client.get(f"{api}/projects/{project['id']}/validation.csv")
    filas = resp.content.decode("utf-8-sig").strip().split("\n")
    evidencia["obtenido"] = f"HTTP {resp.status_code}, {resp.headers['content-type']}, filas={len(filas)}"
    assert resp.status_code == 200 and resp.headers["content-type"].startswith("text/csv")
    assert len(filas) == 9
