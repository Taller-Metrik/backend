"""Pruebas de integración: descarga del DXF desde la API."""

import io

import ezdxf
import pytest

from tests.helpers import AMBIENTE_L


async def _crear_recorrido(auth_client, project, api) -> dict:
    resp = await auth_client.post(
        f"{api}/projects/{project['id']}/surveys",
        json={"name": "Aula Ñandú 2", "mode": "imported", "corners": AMBIENTE_L, "scale_denominator": 50},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.mark.evidencia(
    id="BI-19",
    nombre="GET /surveys/{id}/export/dxf descarga el plano",
    requisito="RF-04, RF-12",
    objetivo="Verificar que la API entrega el DXF del recorrido guardado como archivo adjunto.",
    entrada="Recorrido 'Aula Ñandú 2' (ambiente en L) guardado a escala 1:50",
    esperado="HTTP 200, application/dxf, nombre de archivo seguro y DXF legible con 6 cotas",
)
async def test_descarga_dxf(auth_client, project, api, evidencia):
    survey = await _crear_recorrido(auth_client, project, api)
    resp = await auth_client.get(f"{api}/surveys/{survey['id']}/export/dxf")
    doc = ezdxf.read(io.StringIO(resp.content.decode("utf-8")))
    cotas = len(doc.modelspace().query("DIMENSION"))
    evidencia["obtenido"] = (
        f"HTTP {resp.status_code}, {resp.headers['content-type']}, "
        f"{resp.headers['content-disposition']}, cotas={cotas}"
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/dxf"
    assert 'filename="metrik_aula_nandu_2_1-50.dxf"' in resp.headers["content-disposition"]
    assert cotas == 6


@pytest.mark.evidencia(
    id="BI-20",
    nombre="Exportar DXF con otra escala",
    requisito="RF-10",
    objetivo="Verificar que se puede pedir el DXF en una escala distinta a la guardada.",
    entrada="GET /surveys/{id}/export/dxf?scale=100",
    esperado="HTTP 200, rótulo con 'Escala 1:100' y nombre con 1-100",
)
async def test_dxf_otra_escala(auth_client, project, api, evidencia):
    survey = await _crear_recorrido(auth_client, project, api)
    resp = await auth_client.get(f"{api}/surveys/{survey['id']}/export/dxf", params={"scale": 100})
    textos = [t.dxf.text for t in ezdxf.read(io.StringIO(resp.text)).modelspace().query("TEXT")]
    evidencia["obtenido"] = f"HTTP {resp.status_code}, {resp.headers['content-disposition']}"
    assert resp.status_code == 200
    assert any("Escala 1:100" in t for t in textos)
    assert "1-100.dxf" in resp.headers["content-disposition"]


@pytest.mark.evidencia(
    id="BI-21",
    nombre="DXF de un recorrido ajeno o inexistente",
    requisito="RNF-07",
    objetivo="Verificar que no se puede descargar el plano de otro usuario.",
    entrada="GET /surveys/9999/export/dxf",
    esperado="HTTP 404",
)
async def test_dxf_inexistente(auth_client, api, evidencia):
    resp = await auth_client.get(f"{api}/surveys/9999/export/dxf")
    evidencia["obtenido"] = f"HTTP {resp.status_code}"
    assert resp.status_code == 404
