"""Genera la evidencia de cada prueba del backend: captura (.png) + descripción (.txt).

Pasos:
1. Ejecuta toda la suite con `--evidencias` (registra metadatos y resultados).
2. Vuelve a ejecutar cada prueba por separado y guarda su salida real de consola como
   imagen con apariencia de terminal (la captura muestra el comando y el resultado).
3. Escribe el .txt de cada prueba y el índice evidencias/backend/README.md.

Uso (desde backend/):
    .venv/Scripts/python scripts/generar_evidencias.py
    # Integración y funcionales contra PostgreSQL real:
    set TEST_DATABASE_URL=postgresql+asyncpg://usuario:clave@localhost:5432/metrik_test
"""

import json
import os
import re
import subprocess
import sys
import textwrap
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
EVIDENCIAS = REPO / "evidencias" / "backend"
RESULTADOS = REPO / "evidencias" / "_resultados" / "backend.json"
PYTHON = sys.executable

TIPOS = {
    "BU": ("unitarias", "Unitaria (backend)"),
    "BI": ("integracion", "Integración (backend)"),
    "BF": ("funcionales", "Funcional (backend)"),
}

# ---------------------------------------------------------------- render de terminal

FONT_DIR = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
COLS = 118
BG = (12, 12, 12)
TITLE_BG = (32, 32, 32)
FG = (204, 204, 204)
GREEN = (22, 198, 12)
RED = (231, 72, 86)
YELLOW = (249, 241, 165)
CYAN = (97, 214, 214)
GREY = (118, 118, 118)


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(str(FONT_DIR / name), size)
    except OSError:
        return ImageFont.load_default(size)


MONO = _font("consola.ttf", 16)
MONO_B = _font("consolab.ttf", 16)
UI = _font("segoeui.ttf", 14)


def _color(line: str) -> tuple[tuple[int, int, int], bool]:
    if line.startswith("PS "):
        return YELLOW, False
    if re.search(r"\bFAILED\b|\bERROR\b|failed", line):
        return RED, True
    if re.search(r"\bPASSED\b|\d+ passed", line):
        return GREEN, True
    if line.startswith(("=", "_")):
        return CYAN, False
    if line.startswith(("platform", "cachedir", "rootdir", "configfile", "plugins", "collected", "asyncio")):
        return GREY, False
    return FG, False


def render_terminal(lines: list[str], title: str, destino: Path) -> None:
    wrapped: list[str] = []
    for line in lines:
        wrapped.extend(textwrap.wrap(line, COLS, replace_whitespace=False, drop_whitespace=False) or [""])
    line_h, pad, title_h = 21, 16, 34
    width = int(MONO.getlength("M") * COLS) + 2 * pad
    height = title_h + pad * 2 + line_h * len(wrapped)
    img = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, width, title_h], fill=TITLE_BG)
    draw.text((14, 8), title, font=UI, fill=(230, 230, 230))
    for i, glyph in enumerate(("—", "☐", "✕")):
        draw.text((width - 110 + i * 36, 7), glyph, font=UI, fill=(200, 200, 200))
    y = title_h + pad
    for line in wrapped:
        color, bold = _color(line)
        draw.text((pad, y), line, font=MONO_B if bold else MONO, fill=color)
        y += line_h
    destino.parent.mkdir(parents=True, exist_ok=True)
    img.save(destino, optimize=True)


# ---------------------------------------------------------------- ejecución


def run(args: list[str]) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PY_COLORS": "0", "COLUMNS": str(COLS)}
    return subprocess.run(args, cwd=BACKEND, capture_output=True, text=True, encoding="utf-8", env=env)


def slug(texto: str) -> str:
    import unicodedata

    s = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-zA-Z0-9]+", "_", s).strip("_").lower()[:60]


def descripcion(r: dict, tipo: str, archivo_png: str) -> str:
    campos = [
        ("ID", r["id"]),
        ("Nombre", r["nombre"]),
        ("Tipo", tipo),
        ("Requisito", r.get("requisito") or "-"),
        ("Archivo", r["nodeid"].replace("::", " :: ")),
        ("Objetivo", r.get("objetivo") or "-"),
        ("Precondiciones", r.get("precondiciones") or "Ninguna."),
        ("Datos de entrada", r.get("entrada") or "-"),
        ("Resultado esperado", r.get("esperado") or "-"),
        ("Resultado obtenido", r.get("obtenido") or "-"),
        ("Estado", r["estado"]),
        ("Duración", f"{r.get('duracion_s', 0):.3f} s"),
        ("Base de datos", os.environ.get("TEST_DATABASE_URL", "SQLite en memoria").split("@")[-1]),
        ("Fecha", r["fecha"]),
        ("Captura", archivo_png),
    ]
    ancho = max(len(k) for k, _ in campos) + 2
    out = []
    for k, v in campos:
        lineas = textwrap.wrap(str(v), 100 - ancho) or [""]
        out.append(f"{k + ':':<{ancho}}{lineas[0]}")
        out.extend(" " * ancho + extra for extra in lineas[1:])
    if r.get("detalle_error"):
        out += ["", "Detalle del error:", r["detalle_error"]]
    return "\n".join(out) + "\n"


def main() -> None:
    if RESULTADOS.exists():
        RESULTADOS.unlink()
    print("1/3 Ejecutando la suite completa...")
    suite = run([PYTHON, "-m", "pytest", "--evidencias", "-v", "-p", "no:cacheprovider", "--cov", "--cov-report=term"])
    salida_suite = [f"PS {BACKEND}> python -m pytest -v --cov", *suite.stdout.rstrip().splitlines()]
    render_terminal(salida_suite[-60:], "Windows PowerShell — MetriK backend — suite completa", EVIDENCIAS / "00_suite_completa.png")
    (EVIDENCIAS / "00_suite_completa.txt").write_text(suite.stdout, encoding="utf-8")

    registros = json.loads(RESULTADOS.read_text(encoding="utf-8"))
    print(f"2/3 Generando captura y descripción de {len(registros)} pruebas...")
    indice = []
    for r in registros:
        carpeta, tipo = TIPOS[r["id"][:2]]
        base = f"{r['id']}_{slug(r['nombre'])}"
        png = EVIDENCIAS / carpeta / f"{base}.png"
        res = run([PYTHON, "-m", "pytest", r["nodeid"], "-v", "-p", "no:cacheprovider", "--no-header", "-rA"])
        lineas = [f'PS {BACKEND}> python -m pytest "{r["nodeid"]}" -v', *res.stdout.rstrip().splitlines()]
        lineas = [ln for ln in lineas if not ln.startswith("PASSED ")]  # duplicado del resumen -rA
        render_terminal(lineas, f"Windows PowerShell — {r['id']} · {r['nombre']}", png)
        (png.with_suffix(".txt")).write_text(descripcion(r, tipo, png.name), encoding="utf-8")
        indice.append((r, carpeta, base))
        print(f"   {r['id']} {r['estado']}")

    print("3/3 Escribiendo índice...")
    aprobados = sum(1 for r, _, _ in indice if r["estado"] == "APROBADO")
    filas = "\n".join(
        f"| {r['id']} | [{r['nombre']}]({c}/{b}.png) | {TIPOS[r['id'][:2]][1].split(' ')[0]} | {r.get('requisito', '')} | "
        f"{'✅' if r['estado'] == 'APROBADO' else '❌'} {r['estado']} |"
        for r, c, b in indice
    )
    cobertura = next((ln for ln in suite.stdout.splitlines() if ln.startswith("TOTAL")), "")
    (EVIDENCIAS / "README.md").write_text(
        f"""# Evidencias de pruebas — Backend

Generado: {datetime.now():%Y-%m-%d %H:%M} · Base de datos: {os.environ.get("TEST_DATABASE_URL", "SQLite en memoria").split("@")[-1]}

**{aprobados} de {len(indice)} pruebas aprobadas.** Cobertura: `{cobertura}`

Cada prueba tiene una captura de su ejecución (`.png`) y su descripción (`.txt`) con el mismo nombre.
Ejecución completa: [`00_suite_completa.png`](00_suite_completa.png).

| ID | Prueba | Tipo | Requisito | Estado |
|----|--------|------|-----------|--------|
{filas}
""",
        encoding="utf-8",
    )
    print(f"Listo: {aprobados}/{len(indice)} aprobadas → {EVIDENCIAS}")
    if aprobados != len(indice):
        sys.exit(1)


if __name__ == "__main__":
    main()
