"""The Design tab's server half (docs/whiteboard-plan.md): a document model, a KiCad
writer/reader for it, a grid router and the live fabrication-rule checks.

Everything here works in the document's own units (mm) and KiCad's coordinate
convention (X right, Y down), so a document's numbers can be copied straight into a
`.kicad_pcb` and back without a sign flip.
"""
from __future__ import annotations

import heapq
import math
from pathlib import Path
from typing import Annotated, Literal, Optional, Union

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, ValidationError
from shapely.geometry import LinearRing, LineString, Point as SPoint, Polygon
from shapely.ops import nearest_points, unary_union

from kicad2cad.geom import arc_points
from kicad2cad.parse import ParseError, load as load_kicad

from .storage import Storage

Point = tuple[float, float]


class DesignError(ValueError):
    """A document parses fine as JSON but breaks a modelling rule (bad id, net, shape...)."""


# ---- document model ---------------------------------------------------------------------------

class Net(BaseModel):
    name: str
    color: str = "#888888"


class Outline(BaseModel):
    points: list[Point]


class Trace(BaseModel):
    id: str
    kind: Literal["trace"] = "trace"
    net: str
    width: float
    points: list[Point]


class Hole(BaseModel):
    id: str
    kind: Literal["hole"] = "hole"
    d: float
    at: Point
    role: str = ""
    net: Optional[str] = None


DesignObject = Annotated[Union[Trace, Hole], Field(discriminator="kind")]


class Document(BaseModel):
    version: int = 1
    units: str = "mm"
    grid: float = 1.0
    outline: Outline
    nets: list[Net] = Field(default_factory=list)
    objects: list[DesignObject] = Field(default_factory=list)


def _closed_dedup(points) -> list[Point]:
    """An outline's points, with a repeated closing point (if any) dropped."""
    pts = [tuple(p) for p in points]
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    return pts


def outline_polygon(outline: Outline) -> Polygon:
    """The outline as a shapely Polygon, or a DesignError naming what's wrong with it."""
    pts = _closed_dedup(outline.points)
    if len(pts) < 3:
        raise DesignError("outline: needs at least 3 points")
    ring = LinearRing(pts)
    if not ring.is_simple:
        raise DesignError("outline: edges cross themselves, not a simple polygon")
    poly = Polygon(ring)
    if not poly.is_valid or poly.area <= 1e-9:
        raise DesignError("outline: not a valid closed polygon (points may be collinear or degenerate)")
    return poly


def validate_document(doc: Document) -> None:
    """Cross-object rules a lone pydantic field can't check. Raises DesignError, never returns a value."""
    seen: set[str] = set()
    for o in doc.objects:
        if o.id in seen:
            raise DesignError(f"duplicate object id {o.id!r}")
        seen.add(o.id)

    net_names = {n.name for n in doc.nets}
    for o in doc.objects:
        if isinstance(o, Trace):
            if o.net not in net_names:
                raise DesignError(f"trace {o.id!r} references unknown net {o.net!r}")
            if o.width <= 0:
                raise DesignError(f"trace {o.id!r}: width must be > 0 (got {o.width})")
            if len(o.points) < 2:
                raise DesignError(f"trace {o.id!r}: needs at least two points")
        else:
            if o.d <= 0:
                raise DesignError(f"hole {o.id!r}: diameter must be > 0 (got {o.d})")
            if o.net is not None and o.net not in net_names:
                raise DesignError(f"hole {o.id!r} references unknown net {o.net!r}")

    outline_polygon(doc.outline)          # raises DesignError on a bad outline


# ---- document -> .kicad_pcb --------------------------------------------------------------------

# A plain two-layer table is enough for kicad2cad (and real KiCad) to read the file; we only
# ever draw on F.Cu and Edge.Cuts, but a board missing the usual layers looks hand-broken.
_LAYERS = """  (layers
    (0 "F.Cu" signal)
    (2 "B.Cu" signal)
    (9 "F.Adhes" user "F.Adhesive")
    (11 "B.Adhes" user "B.Adhesive")
    (13 "F.Paste" user)
    (15 "B.Paste" user)
    (5 "F.SilkS" user "F.Silkscreen")
    (7 "B.SilkS" user "B.Silkscreen")
    (1 "F.Mask" user)
    (3 "B.Mask" user)
    (25 "Edge.Cuts" user)
    (31 "F.CrtYd" user "F.Courtyard")
    (32 "B.CrtYd" user "B.Courtyard")
    (35 "F.Fab" user)
    (36 "B.Fab" user)
  )"""


def _fmt(v: float) -> str:
    """A trimmed fixed-point number KiCad's own S-expressions use (never scientific notation)."""
    return f"{v:.4f}".rstrip("0").rstrip(".") or "0"


def document_to_kicad(doc: Document) -> str:
    """A document -> a KiCad 9 `.kicad_pcb`: traces become F.Cu segments, the outline becomes
    Edge.Cuts, and holes become non-plated through holes (no copper around them)."""
    validate_document(doc)
    net_index = {n.name: i + 1 for i, n in enumerate(doc.nets)}
    net_lines = ['(net 0 "")'] + [f'(net {idx} "{name}")' for name, idx in net_index.items()]

    body: list[str] = []
    pts = _closed_dedup(doc.outline.points)
    for a, b in zip(pts, pts[1:] + pts[:1]):
        body.append(f'(gr_line (start {_fmt(a[0])} {_fmt(a[1])}) (end {_fmt(b[0])} {_fmt(b[1])}) '
                    f'(stroke (width 0.05) (type solid)) (layer "Edge.Cuts"))')

    for obj in doc.objects:
        if isinstance(obj, Trace):
            idx = net_index[obj.net]
            for a, b in zip(obj.points, obj.points[1:]):
                body.append(f'(segment (start {_fmt(a[0])} {_fmt(a[1])}) (end {_fmt(b[0])} {_fmt(b[1])}) '
                            f'(width {_fmt(obj.width)}) (layer "F.Cu") (net {idx}))')
        else:
            # A hole is mechanical (pogo pin, screw, tape tail), so it is written as a non-plated
            # hole rather than a via: a via would leave a hair-thin copper ring around every hole,
            # which the converter would faithfully turn into an unprintable sliver. The document
            # keeps the hole's net for the rule checks; the board file has no copper there.
            x, y = obj.at
            body.append(f'(footprint "design:hole" (layer "F.Cu") (at {_fmt(x)} {_fmt(y)})\n'
                        f'    (property "Reference" "{obj.id}" (at 0 0 0) (layer "F.SilkS"))\n'
                        f'    (pad "" np_thru_hole circle (at 0 0) (size {_fmt(obj.d)} {_fmt(obj.d)}) '
                        f'(drill {_fmt(obj.d)}) (layers "*.Cu" "*.Mask")))')

    nets_block = "\n".join("  " + l for l in net_lines)
    body_block = "\n".join("  " + l for l in body)
    return f'''(kicad_pcb (version 20241229) (generator "3dpcb-design") (generator_version "9.0")
  (general (thickness 1.6) (legacy_teardrops no))
  (paper "A4")
{_LAYERS}
{nets_block}
{body_block}
)
'''


# ---- .kicad_pcb -> document --------------------------------------------------------------------

def _merge_polylines(edges: list[tuple[Point, Point, float, str | None]]):
    """Chain 2-point (start, end, width, net) segments that share an endpoint, width and net
    into polylines. Greedy and order-preserving, so the result is deterministic; a track with
    more than two segments meeting at one point (a branch) ends up as separate chains, which is
    fine here since KiCad tracks written by `document_to_kicad` never branch."""
    tol = 1e-3   # mm; well inside the 0.01 mm round-trip tolerance we're asked to keep

    def close(p: Point, q: Point) -> bool:
        return abs(p[0] - q[0]) < tol and abs(p[1] - q[1]) < tol

    groups: dict[tuple[str | None, float], list[tuple[Point, Point]]] = {}
    for a, b, width, net in edges:
        groups.setdefault((net, round(width, 4)), []).append((a, b))

    polylines = []
    for (net, width), segs in groups.items():
        remaining = list(segs)
        while remaining:
            chain = list(remaining.pop(0))
            grew = True
            while grew:
                grew = False
                for i, (p, q) in enumerate(remaining):
                    if close(p, chain[-1]):
                        chain.append(q)
                    elif close(q, chain[-1]):
                        chain.append(p)
                    elif close(q, chain[0]):
                        chain.insert(0, p)
                    elif close(p, chain[0]):
                        chain.insert(0, q)
                    else:
                        continue
                    remaining.pop(i)
                    grew = True
                    break
            polylines.append((chain, width, net))
    return polylines


def kicad_to_document(path: str | Path) -> Document:
    """The inverse of document_to_kicad. Only F.Cu tracks, the Edge.Cuts outline and drills map
    onto the four object kinds the Design tab knows; zones, pads' own shapes, copper graphics and
    interior cut-outs in the outline have no equivalent and are dropped (their drills survive, as
    plain holes). Curves are sampled to 0.01 mm rather than kept exact."""
    board = load_kicad(Path(path))

    edges: list[tuple[Point, Point, float, str | None]] = []
    for t in board.tracks:
        if t.layer != "F.Cu":
            continue
        chain = arc_points(t.start, t.mid, t.end, 0.01) if t.mid is not None else [t.start, t.end]
        edges.extend((a, b, t.width, t.net) for a, b in zip(chain, chain[1:]))

    net_names: list[str] = []

    def use_net(name: str | None) -> str | None:
        if name and name not in net_names:
            net_names.append(name)
        return name

    objects: list[Trace | Hole] = []
    for i, (chain, width, net) in enumerate(_merge_polylines(edges)):
        name = use_net(net) or use_net("unnamed")     # a net-less track still needs a document net
        objects.append(Trace(id=f"t{i + 1}", net=name, width=width,
                              points=[[round(x, 4), round(y, 4)] for x, y in chain]))

    for i, d in enumerate(board.drills):
        objects.append(Hole(id=f"h{i + 1}", d=round(d.w, 4), at=[round(d.x, 4), round(d.y, 4)],
                             role="", net=use_net(d.net)))

    outline_pts = [[round(x, 4), round(y, 4)] for x, y in _closed_dedup(list(board.outline.exterior.coords))]

    doc = Document(units="mm", grid=1.0, outline=Outline(points=outline_pts),
                    nets=[Net(name=n) for n in net_names], objects=objects)
    validate_document(doc)
    return doc


# ---- router (grid A*) --------------------------------------------------------------------------

DEFAULT_CLEARANCE = 4.6   # mm; the "gap between different nets" default in docs/whiteboard-plan.md §1


def route(doc: Document, start: Point, end: Point, net: str, clearance: float = DEFAULT_CLEARANCE
          ) -> list[Point] | None:
    """A deterministic A* from `start` to `end` on the document's grid: 8-direction moves (45°
    diagonals allowed), staying inside the outline and at least `clearance` away from copper
    belonging to any *other* net. Copper on `net` itself is never an obstacle. None if walled in."""
    grid = doc.grid or 1.0
    outline_poly = outline_polygon(doc.outline)

    blockers = []
    for o in doc.objects:
        if isinstance(o, Trace) and o.net != net:
            blockers.append(LineString(o.points).buffer(o.width / 2 + clearance))
        elif isinstance(o, Hole) and o.net is not None and o.net != net:
            blockers.append(SPoint(o.at).buffer(o.d / 2 + clearance))
    forbidden = unary_union(blockers) if blockers else None
    allowed = outline_poly.difference(forbidden) if forbidden is not None else outline_poly

    def to_cell(p: Point) -> tuple[int, int]:
        return (round(p[0] / grid), round(p[1] / grid))

    def to_mm(c: tuple[int, int]) -> Point:
        return (c[0] * grid, c[1] * grid)

    def free(c: tuple[int, int]) -> bool:
        return allowed.covers(SPoint(to_mm(c)))

    start_cell, end_cell = to_cell(start), to_cell(end)
    if not free(start_cell) or not free(end_cell):
        return None

    minx, miny, maxx, maxy = outline_poly.bounds
    lo_x, hi_x = math.floor(minx / grid) - 1, math.ceil(maxx / grid) + 1
    lo_y, hi_y = math.floor(miny / grid) - 1, math.ceil(maxy / grid) + 1
    root2 = math.sqrt(2)

    def heuristic(c: tuple[int, int]) -> float:
        dx, dy = abs(c[0] - end_cell[0]), abs(c[1] - end_cell[1])
        return grid * (max(dx, dy) + (root2 - 1) * min(dx, dy))     # octile distance, admissible

    frontier: list[tuple[float, float, tuple[int, int]]] = [(heuristic(start_cell), 0.0, start_cell)]
    came_from: dict[tuple[int, int], tuple[int, int]] = {}
    best_g = {start_cell: 0.0}
    closed: set[tuple[int, int]] = set()

    while frontier:
        _, g, cur = heapq.heappop(frontier)
        if cur in closed:
            continue
        closed.add(cur)
        if cur == end_cell:
            cells = [cur]
            while cells[-1] in came_from:
                cells.append(came_from[cells[-1]])
            cells.reverse()
            return [list(start)] + [list(to_mm(c)) for c in cells[1:-1]] + [list(end)]
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                nxt = (cur[0] + dx, cur[1] + dy)
                if not (lo_x <= nxt[0] <= hi_x and lo_y <= nxt[1] <= hi_y):
                    continue
                if nxt in closed or not free(nxt):
                    continue
                ng = g + grid * (root2 if dx and dy else 1.0)
                if ng < best_g.get(nxt, math.inf):
                    best_g[nxt] = ng
                    came_from[nxt] = cur
                    heapq.heappush(frontier, (ng + heuristic(nxt), ng, nxt))
    return None


# ---- live rule checks --------------------------------------------------------------------------

DEFAULT_RULES = {
    "min_trace_width": 3.0,
    "min_net_gap": 4.6,
    "min_edge_margin": 4.0,
    "min_hole_diameter": 1.0,
    "max_board_size": 180.0,
}


def _issue(rule: str, severity: str, message: str, object_id: str | None = None,
           at: Point | None = None) -> dict:
    return {"rule": rule, "severity": severity, "message": message, "object_id": object_id,
            "at": [round(at[0], 3), round(at[1], 3)] if at is not None else None}


def check_rules(doc: Document, rules: dict | None = None) -> list[dict]:
    """The live checks from docs/whiteboard-plan.md §1. Never raises for a well-formed document;
    call validate_document first if the document itself might be malformed."""
    r = {**DEFAULT_RULES, **(rules or {})}
    outline_poly = outline_polygon(doc.outline)
    minx, miny, maxx, maxy = outline_poly.bounds
    issues = []

    if max(maxx - minx, maxy - miny) > r["max_board_size"]:
        issues.append(_issue("max_board_size", "error",
                              f"board is {maxx - minx:.1f} x {maxy - miny:.1f} mm, over the "
                              f"{r['max_board_size']:g} mm printer bed", at=(minx, miny)))

    traces = [o for o in doc.objects if isinstance(o, Trace)]
    holes = [o for o in doc.objects if isinstance(o, Hole)]

    for t in traces:
        if t.width < r["min_trace_width"]:
            issues.append(_issue("min_trace_width", "warning",
                                  f"trace {t.id!r} is {t.width:g} mm wide, under the "
                                  f"{r['min_trace_width']:g} mm minimum", t.id, t.points[len(t.points) // 2]))

    for h in holes:
        if h.d < r["min_hole_diameter"]:
            issues.append(_issue("min_hole_diameter", "warning",
                                  f"hole {h.id!r} is {h.d:g} mm across, under the "
                                  f"{r['min_hole_diameter']:g} mm minimum", h.id, h.at))

    # copper features tagged with a net, for the inter-net gap and edge-margin checks below
    features = [(t.id, t.net, LineString(t.points).buffer(t.width / 2)) for t in traces]
    features += [(h.id, h.net, SPoint(h.at).buffer(h.d / 2)) for h in holes if h.net is not None]

    for i, (id_a, net_a, geom_a) in enumerate(features):
        for id_b, net_b, geom_b in features[i + 1:]:
            if net_a == net_b:
                continue
            gap = geom_a.distance(geom_b)
            if gap < r["min_net_gap"]:
                pa, pb = nearest_points(geom_a, geom_b)
                issues.append(_issue("min_net_gap", "warning",
                                      f"{net_a!r} and {net_b!r} are {gap:.2f} mm apart, under the "
                                      f"{r['min_net_gap']:g} mm minimum", id_a, ((pa.x + pb.x) / 2, (pa.y + pb.y) / 2)))

    edge = outline_poly.exterior
    for id_a, net_a, geom_a in features:
        rep = geom_a.representative_point()
        if not outline_poly.contains(geom_a):
            issues.append(_issue("min_edge_margin", "error",
                                  f"{id_a!r} extends past the board edge", id_a, (rep.x, rep.y)))
            continue
        d = geom_a.distance(edge)
        if d < r["min_edge_margin"]:
            issues.append(_issue("min_edge_margin", "warning",
                                  f"{id_a!r} is {d:.2f} mm from the board edge, under the "
                                  f"{r['min_edge_margin']:g} mm minimum", id_a, (rep.x, rep.y)))

    return issues


# ---- routes -------------------------------------------------------------------------------------

router = APIRouter()
store = Storage()


class KicadIn(BaseModel):
    document: dict


class ImportIn(BaseModel):
    board_id: str


class RouteIn(BaseModel):
    document: dict
    start: Point
    end: Point
    net: str
    clearance: float | None = None


class RulesIn(BaseModel):
    document: dict
    rules: dict | None = None


def _load_document(raw: dict) -> Document:
    try:
        doc = Document.model_validate(raw)
    except ValidationError as e:
        detail = "; ".join(f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors())
        raise HTTPException(400, detail)
    try:
        validate_document(doc)
    except DesignError as e:
        raise HTTPException(400, str(e))
    return doc


@router.post("/api/design/kicad")
def design_to_kicad(body: KicadIn):
    doc = _load_document(body.document)
    data = document_to_kicad(doc).encode()
    board_id = store.put_board(data, "design.kicad_pcb")
    return {"board_id": board_id, "bytes": len(data)}


@router.post("/api/design/import")
def design_from_kicad(body: ImportIn):
    path = store.board_path(body.board_id)
    if path is None:
        raise HTTPException(404, "unknown board id; upload it again")
    try:
        doc = kicad_to_document(path)
    except ParseError as e:
        raise HTTPException(422, f"could not read that board: {e}")
    return {"document": doc.model_dump(mode="json")}


@router.post("/api/design/route")
def design_route(body: RouteIn):
    doc = _load_document(body.document)
    if body.net not in {n.name for n in doc.nets}:
        raise HTTPException(400, f"unknown net {body.net!r}")
    clearance = DEFAULT_CLEARANCE if body.clearance is None else body.clearance
    if clearance <= 0:
        raise HTTPException(400, "clearance must be > 0")
    points = route(doc, tuple(body.start), tuple(body.end), body.net, clearance)
    if points is None:
        raise HTTPException(422, "no path keeps the required clearance between those two points")
    return {"points": points}


@router.post("/api/design/rules")
def design_rules(body: RulesIn):
    doc = _load_document(body.document)
    return {"issues": check_rules(doc, body.rules)}
