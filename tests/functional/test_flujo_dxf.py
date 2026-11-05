"""Pruebas funcionales: del recorrido al archivo CAD (CU-04)."""

import io
from pathlib import Path

import ezdxf
import pytest

from tests.helpers import AMBIENTE_L, simulate_walk

SALIDA = Path(__file__).resolve().parents[3] / "evidencias" / "backend" / "funcionales"


@pytest.mark.evidencia(
    id="BF-06",
    nombre="Recorrer un ambiente y exportarlo a CAD",
    requisito="CU-04 (RF-01, RF-05, RF-10, RF-12)",
    objetivo="Verificar el caso de uso: recorrido ruidoso → plano suavizado → DXF editable con cotas a escala.",
    precondiciones="Usuario autenticado con un proyecto",
    entrada="Trazo simulado de ambiente en L (6×5 m, 24 m²) con ruido σ=3 cm, exportado a 1:50",
    esperado="DXF legible: 1 polilínea de 6 muros, 6 cotas cuya suma ≈ 22 m (± 2 %), área en el texto",
)
async def test_recorrido_a_cad(auth_client, project, api, evidencia):
    survey = (
        await auth_client.post(
            f"{api}/projects/{project['id']}/surveys",
            json={"name": "Aula L", "points": simulate_walk(AMBIENTE_L, seed=9), "scale_denominator": 50},
        )
    ).json()
    resp = await auth_client.get(f"{api}/surveys/{survey['id']}/export/dxf")
    doc = ezdxf.read(io.StringIO(resp.text))
    msp = doc.modelspace()
    muros = msp.query('LWPOLYLINE[layer=="MUROS"]')[0]
    cotas = [d.get_measurement() for d in msp.query("DIMENSION")]
    textos = [t.dxf.text for t in msp.query('TEXT[layer=="TEXTO"]')]

    SALIDA.mkdir(parents=True, exist_ok=True)
    (SALIDA / "BF-06_plano_generado.dxf").write_bytes(resp.content)  # para abrirlo en LibreCAD/AutoCAD

    evidencia["obtenido"] = (
        f"muros={len(muros)}, cotas={[round(c, 2) for c in cotas]} (suma {sum(cotas):.2f} m), textos={textos}; "
        f"archivo guardado en evidencias/backend/funcionales/BF-06_plano_generado.dxf"
    )
    assert resp.status_code == 200
    assert len(muros) == 6 and len(cotas) == 6
    assert sum(cotas) == pytest.approx(22.0, rel=0.02)
    assert any(t.startswith("Area:") for t in textos)
