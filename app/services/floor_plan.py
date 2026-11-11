"""Plano de vivienda con varios ambientes (CU-08, RF-25, RF-26).

Cada ambiente se mide por separado en sus propias coordenadas. Para unir el ambiente B al A por un muro
compartido se aplica una **transformación rígida** (rotación + traslación, sin deformar): el muro de B queda
paralelo al de A, en sentido opuesto, centrado y separado por el espesor del muro, del lado de afuera de A.
Las posiciones se propagan desde el primer ambiente (base) recorriendo las uniones.

Controles de calidad (advertencias): muros unidos de largo distinto (> 10 cm, EX-10), ambientes que se
superponen (EX-11), esquinas fuera de escuadra (> 2° de un múltiplo de 90°), uniones que no cierran en un
ciclo y ambientes sin unir (no se incluyen).
"""

import io
import math
from dataclasses import dataclass, field

import ezdxf

from app.services.geometry import GeometryError, Point, _segments_intersect, interior_angles, signed_area
from app.services.scale import validate_scale

LENGTH_TOLERANCE_M = 0.10
SQUARE_TOLERANCE_DEG = 2.0
MAX_THICKNESS_M = 0.50


@dataclass(frozen=True)
class Room:
    survey_id: int
    name: str
    vertices: list[Point]


@dataclass(frozen=True)
class Join:
    a_survey: int
    a_wall: int  # muro i = del vértice i+1 al i+2 (0 = del vértice 1 al 2)
    b_survey: int
    b_wall: int
    thickness_m: float


@dataclass(frozen=True)
class PlacedRoom:
    survey_id: int
    name: str
    vertices: list[Point]
    area_m2: float


@dataclass(frozen=True)
class FloorPlan:
    rooms: list[PlacedRoom]
    total_area_m2: float
    warnings: list[str] = field(default_factory=list)


def _wall(v: list[Point], i: int) -> tuple[Point, Point]:
    return v[i], v[(i + 1) % len(v)]


def _mid(a: Point, b: Point) -> Point:
    return (a[0] + b[0]) / 2, (a[1] + b[1]) / 2


def _centroid(v: list[Point]) -> Point:
    return sum(p[0] for p in v) / len(v), sum(p[1] for p in v) / len(v)


def _transform(v: list[Point], theta: float, dx: float, dy: float) -> list[Point]:
    c, s = math.cos(theta), math.sin(theta)
    return [(x * c - y * s + dx, x * s + y * c + dy) for x, y in v]


def _outward_normal(a: list[Point], i: int) -> Point:
    (x1, y1), (x2, y2) = _wall(a, i)
    length = math.hypot(x2 - x1, y2 - y1)
    nx, ny = (y2 - y1) / length, -(x2 - x1) / length  # a la derecha del sentido del muro
    return (nx, ny) if signed_area(a) > 0 else (-nx, -ny)  # antihorario: el interior está a la izquierda


def place_room(a_world: list[Point], a_wall: int, b_local: list[Point], b_wall: int, thickness_m: float) -> list[Point]:
    """Ubica B pegado al muro `a_wall` de A, del lado de afuera y a `thickness_m` de distancia."""
    n = _outward_normal(a_world, a_wall)
    nb = _outward_normal(b_local, b_wall)
    mid_a = _mid(*_wall(a_world, a_wall))
    target = (mid_a[0] + n[0] * thickness_m, mid_a[1] + n[1] * thickness_m)
    # Se gira B hasta que la normal de afuera de su muro apunte hacia A (opuesta a la de A). Se usa la normal y
    # no el centroide porque en un ambiente cóncavo el centroide puede caer del otro lado del muro.
    theta = math.atan2(-n[1], -n[0]) - math.atan2(nb[1], nb[0])
    rotated = _transform(b_local, theta, 0, 0)
    mid_b = _mid(*_wall(rotated, b_wall))
    return _transform(rotated, 0, target[0] - mid_b[0], target[1] - mid_b[1])


def _inside(p: Point, poly: list[Point]) -> bool:
    inside = False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1], strict=True):
        if (y1 > p[1]) != (y2 > p[1]) and p[0] < (x2 - x1) * (p[1] - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def _overlap(a: list[Point], b: list[Point]) -> bool:
    """Superposición de áreas (tocarse en un borde no cuenta)."""
    if any(_segments_intersect(*_wall(a, i), *_wall(b, j)) for i in range(len(a)) for j in range(len(b))):
        return True

    def pulled(v: list[Point]) -> list[Point]:  # vértices un 1 % hacia el centro: evita falsos positivos en bordes
        c = _centroid(v)
        return [(x + (c[0] - x) * 0.01, y + (c[1] - y) * 0.01) for x, y in v]

    return any(_inside(p, b) for p in pulled(a)) or any(_inside(p, a) for p in pulled(b))


def _validate(rooms: dict[int, Room], joins: list[Join]) -> None:
    for k, j in enumerate(joins, start=1):
        for sid, wall in ((j.a_survey, j.a_wall), (j.b_survey, j.b_wall)):
            if sid not in rooms:
                raise GeometryError(f"La unión {k} usa el ambiente {sid}, que no está en el plano")
            if not 0 <= wall < len(rooms[sid].vertices):
                raise GeometryError(f"La unión {k} usa el muro {wall + 1} de «{rooms[sid].name}», que no existe")
        if not 0 < j.thickness_m <= MAX_THICKNESS_M:
            raise GeometryError(f"El espesor de la unión {k} debe estar entre 0 y {MAX_THICKNESS_M} m")
        if j.a_survey == j.b_survey:
            raise GeometryError(f"La unión {k} une un ambiente consigo mismo")


def _check_join(j: Join, by_id: dict[int, Room], warnings: list[str]) -> None:
    na, nb = by_id[j.a_survey].name, by_id[j.b_survey].name
    la = math.dist(*_wall(by_id[j.a_survey].vertices, j.a_wall))
    lb = math.dist(*_wall(by_id[j.b_survey].vertices, j.b_wall))
    if abs(la - lb) > LENGTH_TOLERANCE_M:
        warnings.append(f"Muros unidos de largo distinto: «{na}» muro {j.a_wall + 1} ({la:.2f} m) y «{nb}» muro "
                        f"{j.b_wall + 1} ({lb:.2f} m): posible esquina mal marcada.")


def build_floor_plan(rooms: list[Room], joins: list[Join]) -> FloorPlan:
    """Planta completa: el primer ambiente es la base; los demás se ubican por sus uniones."""
    if not rooms:
        raise GeometryError("El plano de vivienda necesita al menos un ambiente")
    by_id = {r.survey_id: r for r in rooms}
    _validate(by_id, joins)
    warnings: list[str] = []
    placed: dict[int, list[Point]] = {rooms[0].survey_id: list(rooms[0].vertices)}
    pending = list(joins)
    progress = True
    while progress:
        progress = False
        for j in list(pending):
            a_in, b_in = j.a_survey in placed, j.b_survey in placed
            if not a_in and not b_in:
                continue  # todavía no se puede ubicar: se reintenta en la siguiente vuelta
            if not b_in:
                placed[j.b_survey] = place_room(placed[j.a_survey], j.a_wall, by_id[j.b_survey].vertices, j.b_wall, j.thickness_m)
            elif not a_in:
                placed[j.a_survey] = place_room(placed[j.b_survey], j.b_wall, by_id[j.a_survey].vertices, j.a_wall, j.thickness_m)
            else:
                # Unión de un ciclo: los dos ya están ubicados; se comprueba que los muros queden a la distancia indicada
                gap = math.dist(_mid(*_wall(placed[j.a_survey], j.a_wall)), _mid(*_wall(placed[j.b_survey], j.b_wall)))
                if abs(gap - j.thickness_m) > LENGTH_TOLERANCE_M:
                    warnings.append(f"La unión «{by_id[j.a_survey].name}»–«{by_id[j.b_survey].name}» no cierra "
                                    f"({gap - j.thickness_m:+.2f} m): revisar las medidas.")
            _check_join(j, by_id, warnings)
            pending.remove(j)
            progress = True

    ids = [r.survey_id for r in rooms if r.survey_id in placed]
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            if _overlap(placed[a], placed[b]):
                warnings.append(f"Los ambientes «{by_id[a].name}» y «{by_id[b].name}» se superponen: revisar las uniones.")
    for sid in ids:
        off = [k + 1 for k, ang in enumerate(interior_angles(placed[sid]))
               if abs(ang - 180) > SQUARE_TOLERANCE_DEG and min(abs(ang - m) for m in (90, 270)) > SQUARE_TOLERANCE_DEG]
        if off:
            warnings.append(f"«{by_id[sid].name}» tiene esquinas fuera de escuadra (> 2°) en los vértices {off}.")
    for r in rooms:
        if r.survey_id not in placed:
            warnings.append(f"El ambiente «{r.name}» está sin unir: no se incluye en la planta.")

    placed_rooms = [PlacedRoom(sid, by_id[sid].name, placed[sid], abs(signed_area(placed[sid]))) for sid in ids]
    return FloorPlan(placed_rooms, sum(r.area_m2 for r in placed_rooms), warnings)


def floor_plan_dxf(plan: FloorPlan, title: str, scale_denominator: int = 100) -> str:
    """DXF de la planta: una polilínea por ambiente, su nombre y área, y el cuadro de áreas."""
    denominator = validate_scale(scale_denominator)
    text_h = 2.5 * denominator / 1000  # 2,5 mm en el papel
    doc = ezdxf.new("R2010", setup=True)
    doc.units = ezdxf.units.M
    for name, color in (("AMBIENTES", 7), ("TEXTO", 3), ("CUADRO", 5)):
        doc.layers.add(name, color=color)
    msp = doc.modelspace()
    for r in plan.rooms:
        msp.add_lwpolyline(r.vertices, close=True, dxfattribs={"layer": "AMBIENTES"})
        cx, cy = _centroid(r.vertices)
        msp.add_text(r.name, height=text_h, dxfattribs={"layer": "TEXTO"}).set_placement((cx, cy + text_h * 0.8))
        msp.add_text(f"{r.area_m2:.2f} m2", height=text_h * 0.8, dxfattribs={"layer": "TEXTO"}).set_placement(
            (cx, cy - text_h)
        )
    xs = [x for r in plan.rooms for x, _ in r.vertices] or [0.0]
    ys = [y for r in plan.rooms for _, y in r.vertices] or [0.0]
    x0, y = max(xs) + text_h * 4, max(ys)
    lines = [title, "CUADRO DE AREAS"] + [f"{r.name}: {r.area_m2:.2f} m2" for r in plan.rooms]
    lines.append(f"AREA TOTAL: {plan.total_area_m2:.2f} m2")
    for line in lines:
        msp.add_text(line, height=text_h, dxfattribs={"layer": "CUADRO"}).set_placement((x0, y))
        y -= text_h * 1.6
    stream = io.StringIO()
    doc.write(stream)
    return stream.getvalue()
