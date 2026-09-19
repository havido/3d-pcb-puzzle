"""Read a .kicad_pcb (KiCad 8/9) into a `KicadBoard`."""
import hashlib
from pathlib import Path

from shapely import make_valid
from shapely.geometry import LineString, Polygon
from shapely.ops import polygonize_full, unary_union

from . import sexp
from .geom import arc_points, circle_points, place
from .model import Drill, Graphic, KicadBoard, Pad, Track, Via, Zone
from .sexp import find, first, value, xy

MIN_VERSION = 20240108          # KiCad 8.0
SNAP = 4                        # decimals used to join Edge.Cuts end points (0.1 µm)
GRAPHIC_KINDS = ("line", "arc", "circle", "rect", "poly")


def _preview(text: str, n: int = 24) -> str:
    one_line = " ".join(text.split())
    return one_line if len(one_line) <= n else one_line[:n] + "…"


class ParseError(ValueError):
    pass


class OutlineError(ParseError):
    pass


def load(path: str | Path, arc_chord_mm: float = 0.02) -> KicadBoard:
    path = Path(path)
    return parse_text(path.read_text(encoding="utf-8"), source=str(path), arc_chord_mm=arc_chord_mm)


def parse_text(text: str, source: str = "<string>", arc_chord_mm: float = 0.02) -> KicadBoard:
    tree = sexp.parse(text)
    if tree[0] != "kicad_pcb":
        raise ParseError(f"{source}: not a KiCad board (starts with '{tree[0]}')")
    return _Reader(tree, source, hashlib.sha256(text.encode()).hexdigest(), arc_chord_mm).read()


class _Reader:
    def __init__(self, tree, source, sha, chord):
        self.tree, self.source, self.sha, self.chord = tree, source, sha, chord
        self.warnings: list[str] = []
        self.nets = {n[1]: n[2] for n in find(tree, "net") if len(n) >= 3}
        layers = first(tree, "layers") or []
        self.copper = [l[1] for l in layers[1:] if isinstance(l, list) and l[1].endswith(".Cu")] or ["F.Cu", "B.Cu"]
        self.edge_lines: list[LineString] = []
        self.edge_rings: list[Polygon] = []

    # ---- helpers -------------------------------------------------------------------------
    def warn(self, msg: str):
        self.warnings.append(msg)

    def net(self, node) -> str | None:
        n = first(node, "net")
        if n is None:
            return None
        name = n[2] if len(n) >= 3 else self.nets.get(n[1], n[1])
        return name or None

    def expand_layers(self, names) -> list[str]:
        out = []
        for name in names:
            if name == "*.Cu":
                out += self.copper
            elif name == "F&B.Cu":
                out += ["F.Cu", "B.Cu"]
            elif name in self.copper:
                out.append(name)
        return list(dict.fromkeys(out))

    @staticmethod
    def stroke_width(node) -> float:
        stroke = first(node, "stroke")
        w = value(stroke, "width") if stroke else value(node, "width")
        return float(w) if w is not None else 0.0

    @staticmethod
    def filled(node) -> bool:
        return value(node, "fill") in ("yes", "solid")

    def pts(self, node) -> list:
        """Points of a (pts (xy ..) (arc (start)(mid)(end)) ..) list, arcs sampled."""
        out = []
        for p in (first(node, "pts") or [])[1:]:
            if p[0] == "xy":
                out.append((float(p[1]), float(p[2])))
            elif p[0] == "arc":
                a = arc_points(xy(first(p, "start")), xy(first(p, "mid")), xy(first(p, "end")), self.chord)
                out += a if not out or out[-1] != a[0] else a[1:]
        return out

    def shape_points(self, node, kind, tf=None):
        """(points, closed) for a gr_/fp_ shape; `tf` maps footprint-local points to the board."""
        t = tf or (lambda p: p)
        if kind == "line":
            return [t(xy(first(node, "start"))), t(xy(first(node, "end")))], False
        if kind == "arc":
            s, m, e = (t(xy(first(node, k))) for k in ("start", "mid", "end"))
            return arc_points(s, m, e, self.chord), False
        if kind == "circle":
            c, e = t(xy(first(node, "center"))), t(xy(first(node, "end")))
            r = ((c[0] - e[0]) ** 2 + (c[1] - e[1]) ** 2) ** 0.5
            return circle_points(c[0], c[1], r, self.chord), True
        if kind == "rect":
            (x0, y0), (x1, y1) = xy(first(node, "start")), xy(first(node, "end"))
            corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
            return [t(p) for p in corners] + [t(corners[0])], True
        if kind == "poly":
            p = [t(q) for q in self.pts(node)]
            return p + p[:1], True
        raise ValueError(kind)

    # ---- sections -------------------------------------------------------------------------
    def read(self) -> KicadBoard:
        version = int(value(self.tree, "version", "0"))
        if version < MIN_VERSION:
            self.warn(f"file format {version} is older than KiCad 8 ({MIN_VERSION}); results may be incomplete")
        board = KicadBoard(source=self.source, sha256=self.sha, version=version,
                           generator_version=value(self.tree, "generator_version"),
                           copper_layers=self.copper, outline=Polygon())
        self.read_graphics(board)
        self.read_tracks(board)
        self.read_vias(board)
        self.read_footprints(board)
        self.read_zones(board)
        board.outline = self.build_outline()
        board.warnings = self.warnings
        return board

    def add_shape(self, board, node, kind, layer, tf=None):
        if layer == "Edge.Cuts":
            points, closed = self.shape_points(node, kind, tf)
            if closed:
                self.edge_rings.append(Polygon(points))
            else:
                self.edge_lines.append(LineString([(round(x, SNAP), round(y, SNAP)) for x, y in points]))
        elif layer in self.copper or layer.startswith("User."):
            points, closed = self.shape_points(node, kind, tf)
            g = Graphic(kind, layer, points, self.stroke_width(node), self.filled(node), closed)
            if layer in self.copper:
                board.graphics.append(g)
            else:
                board.user_layers.setdefault(layer, []).append(g)

    def read_graphics(self, board):
        for kind in GRAPHIC_KINDS:
            for node in find(self.tree, f"gr_{kind}"):
                self.add_shape(board, node, kind, value(node, "layer", ""))
        for kind in ("gr_text", "gr_text_box"):
            for node in find(self.tree, kind):
                if value(node, "layer", "") in self.copper:
                    self.warn(f"{kind} '{_preview(node[1])}' on {value(node, 'layer')} is not converted (text needs font outlines)")

    def read_tracks(self, board):
        for node in find(self.tree, "segment"):
            board.tracks.append(Track(value(node, "layer"), self.net(node), float(value(node, "width")),
                                      xy(first(node, "start")), xy(first(node, "end"))))
        for node in find(self.tree, "arc"):
            board.tracks.append(Track(value(node, "layer"), self.net(node), float(value(node, "width")),
                                      xy(first(node, "start")), xy(first(node, "end")), xy(first(node, "mid"))))

    def read_vias(self, board):
        for node in find(self.tree, "via"):
            (x, y), net = xy(first(node, "at")), self.net(node)
            drill = float(value(node, "drill"))
            layers = self.expand_layers((first(node, "layers") or ["layers", "F.Cu", "B.Cu"])[1:])
            board.vias.append(Via(x, y, float(value(node, "size")), drill, layers, net))
            board.drills.append(Drill(x, y, drill, drill, 0.0, True, net))

    def read_footprints(self, board):
        for fp in find(self.tree, "footprint"):
            at = first(fp, "at")
            fx, fy = float(at[1]), float(at[2])
            frot = float(at[3]) if len(at) > 3 else 0.0
            ref = next((p[2] for p in find(fp, "property") if p[1] == "Reference"), None)
            if ref is None:
                ref = next((t[2] for t in find(fp, "fp_text") if t[1] == "reference"), None)
            tf = lambda p, fx=fx, fy=fy, frot=frot: place(fx, fy, frot, p[0], p[1])
            for pad in find(fp, "pad"):
                self.read_pad(board, pad, ref, fx, fy, frot)
            for kind in GRAPHIC_KINDS:
                for node in find(fp, f"fp_{kind}"):
                    self.add_shape(board, node, kind, value(node, "layer", ""), tf)
            for node in find(fp, "fp_text"):
                if value(node, "layer", "") in self.copper:
                    self.warn(f"text '{_preview(node[2])}' on {value(node, 'layer')} in {ref} is not converted")

    def read_pad(self, board, node, ref, fx, fy, frot):
        number, kind, shape = node[1], node[2], node[3]
        at = first(node, "at")
        x, y = place(fx, fy, frot, float(at[1]), float(at[2]))
        angle = float(at[3]) if len(at) > 3 else 0.0
        size = first(node, "size")
        net = self.net(node)
        drill = None
        d = first(node, "drill")
        if d is not None and len(d) > 1:
            if d[1] == "oval":
                dw, dh = float(d[2]), float(d[3] if len(d) > 3 and not isinstance(d[3], list) else d[2])
            else:
                dw = dh = float(d[1])
            off = xy(first(d, "offset")) or (0.0, 0.0)
            dx, dy = place(x, y, angle, off[0], off[1])
            drill = Drill(dx, dy, dw, dh, angle, kind != "np_thru_hole", net)
            board.drills.append(drill)
        if shape in ("custom", "trapezoid"):
            self.warn(f"pad {ref}.{number}: {shape} shape is approximated by its bounding shape")
        board.pads.append(Pad(ref, number, kind, shape, x, y, angle, frot, float(size[1]), float(size[2]),
                              float(value(node, "roundrect_rratio", "0")),
                              self.expand_layers((first(node, "layers") or ["layers"])[1:]), net, drill))

    def read_zones(self, board):
        for z in find(self.tree, "zone"):
            if first(z, "keepout") is not None:
                board.keepouts += 1
                continue
            net = value(z, "net_name") or self.net(z)
            layers = self.expand_layers([value(z, "layer")] if first(z, "layer") else (first(z, "layers") or ["layers"])[1:])
            fills = find(z, "filled_polygon")
            if fills:
                by_layer: dict[str, list[Polygon]] = {}
                for f in fills:
                    poly = make_valid(Polygon(self.pts(f)))
                    by_layer.setdefault(value(f, "layer"), []).append(poly)
                for layer, polys in by_layer.items():
                    if layer in self.copper:
                        board.zones.append(Zone(layer, net, polys))
            else:
                outline = make_valid(Polygon(self.pts(first(z, "polygon"))))
                self.warn(f"zone '{net}' on {', '.join(layers)} has no fill (fill zones in KiCad, press B); using its outline")
                for layer in layers:
                    board.zones.append(Zone(layer, net, [outline]))

    def build_outline(self) -> Polygon:
        polys = list(self.edge_rings)
        if self.edge_lines:
            faces, cuts, dangles, invalid = polygonize_full(unary_union(self.edge_lines))
            if not dangles.is_empty or not cuts.is_empty:
                ends = [c for g in list(getattr(dangles, "geoms", [])) + list(getattr(cuts, "geoms", []))
                        for c in (g.coords[0], g.coords[-1])]
                raise OutlineError(f"{self.source}: board outline is not closed near "
                                   + ", ".join(f"({x:.3f}, {y:.3f})" for x, y in ends[:4]))
            polys += list(getattr(faces, "geoms", []))
        if not polys:
            raise OutlineError(f"{self.source}: no board outline on Edge.Cuts")
        polys.sort(key=lambda p: p.area, reverse=True)
        outer = Polygon(polys[0].exterior)
        holes = []
        for p in polys[1:]:
            ring = Polygon(p.exterior)
            if outer.contains(ring):
                if not any(Polygon(h).contains(ring) or Polygon(h).equals(ring) for h in holes):
                    holes.append(p.exterior)
            else:
                self.warn(f"Edge.Cuts shape near {ring.representative_point().coords[0]} is outside the board and ignored")
        return Polygon(outer.exterior, holes)
