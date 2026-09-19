"""Phase 2: turn a parsed `KicadBoard` into 2D polygons, the `Board2D` model.

`Board2D` is the contract other tools build on (#29 cutter plate, #31 design checks).
Everything stays in KiCad coordinates (mm, Y down).
"""
import math
from dataclasses import dataclass, field

from shapely import affinity, make_valid
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from .geom import angle_step, arc_points
from .model import Drill, Graphic, KicadBoard, Pad

EMPTY = MultiPolygon()


@dataclass
class CopperFeature:
    kind: str                         # track | arc | pad | via | zone | graphic
    layer: str
    net: str | None
    ref: str | None                   # footprint reference for pads
    geom: BaseGeometry                # (Multi)Polygon, KiCad coords


@dataclass
class Board2D:
    source: str
    outline: Polygon                                  # interior cut-outs are its holes
    copper: dict[str, list[CopperFeature]]            # per copper layer, one entry per feature
    merged: dict[str, MultiPolygon]                   # per copper layer: union − drills, clipped to the outline
    drills: list[Drill]
    holes: MultiPolygon                               # all drill shapes
    user_layers: dict[str, MultiPolygon]
    warnings: list[str] = field(default_factory=list)
    markers: list[tuple[float, float, str]] = field(default_factory=list)
    alignment: list[tuple[float, float, float]] = field(default_factory=list)   # cutter pin holes: x, y, Ø (phase 4)


# ---- primitive shapes ---------------------------------------------------------------------------

def _quad_segs(r: float, chord: float) -> int:
    """shapely's circle resolution (segments per quarter) for a chord error of `chord`."""
    return max(4, math.ceil((math.pi / 2) / angle_step(r, chord)))


def capsule(a, b, width: float, chord: float) -> Polygon:
    """A track: the segment a–b thickened to `width` with round ends (how KiCad draws tracks)."""
    r = width / 2
    if a == b:
        return Point(a).buffer(r, quad_segs=_quad_segs(r, chord))
    return LineString([a, b]).buffer(r, quad_segs=_quad_segs(r, chord))


def stroke(points, width: float, chord: float) -> BaseGeometry:
    r = width / 2
    return LineString(points).buffer(r, quad_segs=_quad_segs(r, chord))


def kicad_rotate(geom: BaseGeometry, angle: float, origin) -> BaseGeometry:
    """Rotate by a KiCad angle (counter-clockwise on screen). With Y pointing down, that's a
    negative angle in shapely's maths convention; this matches `geom.place`."""
    return affinity.rotate(geom, -angle, origin=origin) if angle else geom


def stadium(cx: float, cy: float, w: float, h: float, chord: float) -> Polygon:
    """Oval pad/drill: a w × h rectangle with fully rounded short ends."""
    if abs(w - h) < 1e-9:
        return Point(cx, cy).buffer(w / 2, quad_segs=_quad_segs(w / 2, chord))
    if w > h:
        return capsule((cx - (w - h) / 2, cy), (cx + (w - h) / 2, cy), h, chord)
    return capsule((cx, cy - (h - w) / 2), (cx, cy + (h - w) / 2), w, chord)


def roundrect(cx: float, cy: float, w: float, h: float, r: float, chord: float) -> Polygon:
    if r <= 1e-9:
        return box(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
    inner = box(cx - w / 2 + r, cy - h / 2 + r, cx + w / 2 - r, cy + h / 2 - r)
    return inner.buffer(r, quad_segs=_quad_segs(r, chord))


def pad_shape(p: Pad, chord: float) -> BaseGeometry:
    """Copper outline of a pad (before its drill is removed); empty for bare NPTH holes."""
    if p.kind == "np_thru_hole" and p.drill is not None and max(p.w, p.h) <= max(p.drill.w, p.drill.h) + 1e-9:
        return EMPTY
    if p.shape == "circle":
        g = Point(p.x, p.y).buffer(p.w / 2, quad_segs=_quad_segs(p.w / 2, chord))
    elif p.shape == "oval":
        g = stadium(p.x, p.y, p.w, p.h, chord)
    elif p.shape == "roundrect":
        g = roundrect(p.x, p.y, p.w, p.h, p.rratio * min(p.w, p.h), chord)
    else:                              # rect; trapezoid and custom are approximated (parse warned)
        g = box(p.x - p.w / 2, p.y - p.h / 2, p.x + p.w / 2, p.y + p.h / 2)
    return kicad_rotate(g, p.angle, (p.x, p.y))


def drill_shape(d: Drill, chord: float) -> Polygon:
    return kicad_rotate(stadium(d.x, d.y, d.w, d.h, chord), d.angle, (d.x, d.y))


def graphic_shape(g: Graphic, chord: float) -> BaseGeometry:
    if g.closed and g.filled:
        area = make_valid(Polygon(g.points))
        return area.buffer(g.width / 2, quad_segs=_quad_segs(g.width / 2, chord)) if g.width > 0 else area
    if g.width <= 0:
        return EMPTY                   # an unfilled zero-width shape draws nothing
    return stroke(g.points, g.width, chord)


def as_multipolygon(geom: BaseGeometry) -> MultiPolygon:
    if geom.is_empty:
        return EMPTY
    if isinstance(geom, Polygon):
        return MultiPolygon([geom])
    if isinstance(geom, MultiPolygon):
        return geom
    return MultiPolygon([g for g in getattr(geom, "geoms", []) if isinstance(g, Polygon) and not g.is_empty])


# ---- the whole board ----------------------------------------------------------------------------

def to_board2d(b: KicadBoard, chord: float = 0.02, include_zones: bool = True,
               include_copper_graphics: bool = True) -> Board2D:
    copper: dict[str, list[CopperFeature]] = {layer: [] for layer in b.copper_layers}

    def add(kind, layer, net, ref, geom):
        if layer in copper and not geom.is_empty:
            copper[layer].append(CopperFeature(kind, layer, net, ref, geom))

    for t in b.tracks:
        if t.mid is None:
            add("track", t.layer, t.net, None, capsule(t.start, t.end, t.width, chord))
        else:
            add("arc", t.layer, t.net, None, stroke(arc_points(t.start, t.mid, t.end, chord), t.width, chord))
    for p in b.pads:
        shape = pad_shape(p, chord)
        for layer in p.layers:
            add("pad", layer, p.net, p.ref, shape)
    for v in b.vias:
        shape = Point(v.x, v.y).buffer(v.size / 2, quad_segs=_quad_segs(v.size / 2, chord))
        for layer in v.layers:
            add("via", layer, v.net, None, shape)
    if include_zones:
        for z in b.zones:
            add("zone", z.layer, z.net, None, unary_union(z.polygons))
    if include_copper_graphics:
        for g in b.graphics:
            add("graphic", g.layer, None, None, graphic_shape(g, chord))

    warnings = list(b.warnings)
    holes = as_multipolygon(unary_union([drill_shape(d, chord) for d in b.drills]))
    merged = {}
    for layer, feats in copper.items():
        union = unary_union([f.geom for f in feats])
        off_board = [f for f in feats if not f.geom.intersects(b.outline)]
        trimmed = union.difference(b.outline).area
        if trimmed > 0.01:
            refs = sorted({f.ref for f in off_board if f.ref})
            warnings.append(f"{layer}: {trimmed:.1f} mm² of copper lies outside the board edge and was dropped "
                            f"({len(off_board)} feature(s) entirely off-board{': ' + ', '.join(refs) if refs else ''})")
        merged[layer] = as_multipolygon(union.difference(holes).intersection(b.outline))
    user = {layer: as_multipolygon(unary_union([graphic_shape(g, chord) for g in shapes]))
            for layer, shapes in b.user_layers.items()}
    return Board2D(b.source, b.outline, copper, merged, b.drills, holes, user, warnings, list(b.markers))
