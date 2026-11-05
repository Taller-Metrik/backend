"""Escalas de plano y calibración de planos importados (docs/03-algoritmos.md, sección 6)."""

from app.services.geometry import GeometryError, Point, euclidean

STANDARD_SCALES: tuple[int, ...] = (20, 25, 50, 75, 100, 200, 250, 500, 1000, 2000)

# Área útil de dibujo en una hoja A3 horizontal con márgenes y rótulo (mm)
A3_DRAWING_AREA_MM: tuple[float, float] = (380.0, 230.0)


def validate_scale(denominator: int) -> int:
    if denominator not in STANDARD_SCALES:
        raise GeometryError(f"Escala 1:{denominator} no soportada. Use una de {STANDARD_SCALES}")
    return denominator


def to_paper_mm(real_m: float, denominator: int) -> float:
    """Longitud real (m) → longitud en el papel (mm) para la escala 1:denominador."""
    validate_scale(denominator)
    return real_m * 1000.0 / denominator


def to_real_m(paper_mm: float, denominator: int) -> float:
    """Longitud en el papel (mm) → longitud real (m)."""
    validate_scale(denominator)
    return paper_mm * denominator / 1000.0


def suggest_scale(width_m: float, height_m: float, sheet_mm: tuple[float, float] = A3_DRAWING_AREA_MM) -> int:
    """Escala estándar más grande (más detalle) con la que el plano cabe en la hoja."""
    for denominator in STANDARD_SCALES:
        w = to_paper_mm(width_m, denominator)
        h = to_paper_mm(height_m, denominator)
        if (w <= sheet_mm[0] and h <= sheet_mm[1]) or (w <= sheet_mm[1] and h <= sheet_mm[0]):
            return denominator
    return STANDARD_SCALES[-1]


def meters_per_pixel(p1_px: Point, p2_px: Point, real_distance_m: float) -> float:
    """Calibra un plano importado a partir de dos puntos con distancia real conocida (RF-11)."""
    if real_distance_m <= 0:
        raise GeometryError("La distancia real debe ser mayor que cero")
    pixels = euclidean(p1_px, p2_px)
    if pixels == 0:
        raise GeometryError("Los dos puntos de calibración no pueden coincidir")
    return real_distance_m / pixels


def pixels_to_meters(points_px: list[Point], mpp: float) -> list[Point]:
    return [(x * mpp, -y * mpp) for x, y in points_px]  # el eje Y de la imagen apunta hacia abajo
