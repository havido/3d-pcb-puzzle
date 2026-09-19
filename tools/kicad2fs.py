"""KiCad .kicad_pcb -> Onshape FeatureScript.

Layer convention (draw the goose in the SAME coordinates as the badge PCB so the
badge reference sketch lines up):
  Edge.Cuts  board outline + through cut-outs (largest closed shape = the board)
  F.Cu       raised copper islands on top (feathers): zones, polygons, tracks, pads
  B.Cu       back copper (sketch only, or embossed if enabled in the feature)
  User.1     pockets cut into the top face (organ seats)
  drills     every pad drill and via becomes a through hole

Usage:
  python tools/kicad2fs.py goose.kicad_pcb -o goose.fs --ref "Archive 2/badge.kicad_pcb"
"""
import argparse
import math
import re

from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import polygonize, unary_union
from shapely import affinity

ARC_STEP_DEG = 6  # tessellation step for arcs / circles
SNAP = 3          # decimals used to snap Edge.Cuts endpoints together


# ---------- s-expression parsing ----------

def parse_sexpr(text):
    tokens = re.findall(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+', text)
    stack, cur = [], []
    for tok in tokens:
        if tok == '(':
            stack.append(cur)
            cur = []
        elif tok == ')':
            done, cur = cur, stack.pop()
            cur.append(done)
        elif tok[0] == '"':
            cur.append(tok[1:-1])
        else:
            cur.append(tok)
    return cur[0]


def children(node, name):
    return [c for c in node if isinstance(c, list) and c and c[0] == name]


def child(node, name):
    found = children(node, name)
    return found[0] if found else None


def xy(node):
    return float(node[1]), float(node[2])


def layers_of(node):
    lay = child(node, 'layer')
    if lay:
        return lay[1:]
    lay = child(node, 'layers')
    return lay[1:] if lay else []


def on_layer(node, layer):
    for name in layers_of(node):
        if name == layer or (name == '*.Cu' and layer.endswith('.Cu')):
            return True
        if name == 'F&B.Cu' and layer in ('F.Cu', 'B.Cu'):
            return True
    return False


# ---------- geometry helpers (all in KiCad coordinates, Y down) ----------

def arc_points(start, mid, end):
    (x1, y1), (x2, y2), (x3, y3) = start, mid, end
    d = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    if abs(d) < 1e-9:
        return [start, end]
    ux = ((x1**2 + y1**2) * (y2 - y3) + (x2**2 + y2**2) * (y3 - y1) + (x3**2 + y3**2) * (y1 - y2)) / d
    uy = ((x1**2 + y1**2) * (x3 - x2) + (x2**2 + y2**2) * (x1 - x3) + (x3**2 + y3**2) * (x2 - x1)) / d
    r = math.hypot(x1 - ux, y1 - uy)
    a1 = math.atan2(y1 - uy, x1 - ux)
    a2 = math.atan2(y2 - uy, x2 - ux)
    a3 = math.atan2(y3 - uy, x3 - ux)
    # choose the sweep direction that passes through mid
    ccw = (a2 - a1) % (2 * math.pi) < (a3 - a1) % (2 * math.pi)
    sweep = (a3 - a1) % (2 * math.pi) if ccw else -((a1 - a3) % (2 * math.pi))
    n = max(2, int(abs(math.degrees(sweep)) / ARC_STEP_DEG) + 1)
    pts = [(ux + r * math.cos(a1 + sweep * i / n), uy + r * math.sin(a1 + sweep * i / n)) for i in range(n + 1)]
    pts[0], pts[-1] = start, end
    return pts


def bezier_points(p, n=16):
    out = []
    for i in range(n + 1):
        t = i / n
        c = [(1 - t)**3, 3 * (1 - t)**2 * t, 3 * (1 - t) * t**2, t**3]
        out.append((sum(c[k] * p[k][0] for k in range(4)), sum(c[k] * p[k][1] for k in range(4))))
    return out


def pts_of(node):
    """Points of a (pts ...) list, tessellating any embedded arcs."""
    out = []
    for c in child(node, 'pts')[1:]:
        if c[0] == 'xy':
            out.append(xy(c))
        elif c[0] == 'arc':
            out.extend(arc_points(xy(child(c, 'start')), xy(child(c, 'mid')), xy(child(c, 'end'))))
    return out


def graphic_paths(node):
    """(points, closed) for a gr_*/fp_* graphic item, or None."""
    kind = node[0].split('_', 1)[1]
    if kind == 'line':
        return [xy(child(node, 'start')), xy(child(node, 'end'))], False
    if kind == 'arc':
        return arc_points(xy(child(node, 'start')), xy(child(node, 'mid')), xy(child(node, 'end'))), False
    if kind == 'curve':
        return bezier_points(pts_of(node)), False
    if kind == 'poly':
        return pts_of(node), True
    if kind == 'rect':
        (x1, y1), (x2, y2) = xy(child(node, 'start')), xy(child(node, 'end'))
        return [(x1, y1), (x2, y1), (x2, y2), (x1, y2)], True
    if kind == 'circle':
        (cx, cy), (ex, ey) = xy(child(node, 'center')), xy(child(node, 'end'))
        r = math.hypot(ex - cx, ey - cy)
        n = int(360 / ARC_STEP_DEG)
        return [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)], True
    return None


def stroke_width(node, default=0.0):
    w = child(node, 'width')
    if w:
        return float(w[1])
    s = child(node, 'stroke')
    if s and child(s, 'width'):
        return float(child(s, 'width')[1])
    return default


def place(pt, fp_at):
    """Footprint-local point -> board coordinates."""
    if fp_at is None:
        return pt
    a = math.radians(-fp_at[2])
    return (fp_at[0] + pt[0] * math.cos(a) - pt[1] * math.sin(a),
            fp_at[1] + pt[0] * math.sin(a) + pt[1] * math.cos(a))


def at_of(node):
    at = child(node, 'at')
    return (float(at[1]), float(at[2]), float(at[3]) if len(at) > 3 and re.match(r'^-?[\d.]+$', at[3]) else 0.0)


def pad_shape(pad, fp_at):
    px, py, pang = at_of(pad)
    sx, sy = xy(child(pad, 'size'))
    shape = pad[3]
    if shape == 'circle':
        geom = Point(0, 0).buffer(sx / 2)
    elif shape == 'oval':
        r = min(sx, sy) / 2
        half = (max(sx, sy) / 2 - r)
        line = LineString([(-half, 0), (half, 0)] if sx >= sy else [(0, -half), (0, half)])
        geom = line.buffer(r) if half > 0 else Point(0, 0).buffer(r)
    else:  # rect, roundrect, trapezoid, custom -> bounding rectangle
        geom = box(-sx / 2, -sy / 2, sx / 2, sy / 2)
    # pad angle in the file is absolute; position is footprint-relative
    geom = affinity.rotate(geom, -pang, origin=(0, 0))
    cx, cy = place((px, py), fp_at)
    return affinity.translate(geom, cx, cy), (cx, cy)


# ---------- board extraction ----------

def extract(pcb, copper_layers=('F.Cu', 'B.Cu'), extra_layers=('User.1',)):
    edge_lines, holes = [], []
    shapes = {name: [] for name in copper_layers + extra_layers}

    def add_graphic(node, fp_at):
        res = graphic_paths(node)
        if not res:
            return
        pts, closed = res
        pts = [place(p, fp_at) for p in pts]
        if on_layer(node, 'Edge.Cuts'):
            ring = pts + [pts[0]] if closed else pts
            edge_lines.append(LineString([(round(x, SNAP), round(y, SNAP)) for x, y in ring]))
        for name in shapes:
            if not on_layer(node, name):
                continue
            w = stroke_width(node)
            fill = child(node, 'fill')
            filled = closed and (name not in copper_layers or (fill and fill[1] in ('solid', 'yes')) or node[0].endswith('poly'))
            if filled and len(pts) >= 3:
                geom = Polygon(pts).buffer(0)
                if w > 0:
                    geom = geom.buffer(w / 2)
            elif w > 0:
                geom = LineString(pts + [pts[0]] if closed else pts).buffer(w / 2)
            elif closed and len(pts) >= 3:
                geom = Polygon(pts).buffer(0)
            else:
                continue
            shapes[name].append(geom)

    for node in pcb[1:]:
        if not isinstance(node, list):
            continue
        tag = node[0]
        if tag.startswith('gr_'):
            add_graphic(node, None)
        elif tag == 'segment':
            geom = LineString([xy(child(node, 'start')), xy(child(node, 'end'))]).buffer(float(child(node, 'width')[1]) / 2)
            for name in copper_layers:
                if on_layer(node, name):
                    shapes[name].append(geom)
        elif tag == 'arc':
            pts = arc_points(xy(child(node, 'start')), xy(child(node, 'mid')), xy(child(node, 'end')))
            geom = LineString(pts).buffer(float(child(node, 'width')[1]) / 2)
            for name in copper_layers:
                if on_layer(node, name):
                    shapes[name].append(geom)
        elif tag == 'via':
            x, y = xy(child(node, 'at'))
            holes.append((x, y, float(child(node, 'drill')[1])))
            pad = Point(x, y).buffer(float(child(node, 'size')[1]) / 2)
            for name in copper_layers:
                shapes[name].append(pad)
        elif tag == 'zone':
            for poly in children(node, 'polygon'):
                geom = Polygon(pts_of(poly)).buffer(0)
                for name in shapes:
                    if on_layer(node, name):
                        shapes[name].append(geom)
        elif tag == 'footprint':
            fp_at = at_of(node)
            for sub in node[1:]:
                if not isinstance(sub, list):
                    continue
                if sub[0].startswith('fp_') and sub[0] != 'fp_text':
                    add_graphic(sub, fp_at)
                elif sub[0] == 'pad':
                    geom, (cx, cy) = pad_shape(sub, fp_at)
                    drill = child(sub, 'drill')
                    if drill:
                        nums = [float(t) for t in drill[1:] if isinstance(t, str) and re.match(r'^[\d.]+$', t)]
                        if nums:
                            holes.append((cx, cy, min(nums)))
                    for name in copper_layers:
                        if on_layer(sub, name):
                            shapes[name].append(geom)

    faces = list(polygonize(unary_union(edge_lines))) if edge_lines else []
    board = max(faces, key=lambda p: p.area) if faces else None
    merged = {name: unary_union(geoms) if geoms else None for name, geoms in shapes.items()}
    return board, merged, holes


BADGE_CENTRE = (103.4, 103.6)


def rotate_pt(pt, turns):
    """Rotate a KiCad point about the badge centre by turns x 90 deg (positive = badge top swings to the left on screen)."""
    x, y = pt[0] - BADGE_CENTRE[0], pt[1] - BADGE_CENTRE[1]
    for _ in range(turns % 4):
        x, y = y, -x
    return (BADGE_CENTRE[0] + x, BADGE_CENTRE[1] + y)


def reference(pcb, turns=0):
    """Badge outline, switch bodies, switch pads and LEDs as plain loops."""
    return [[rotate_pt(p, turns) for p in loop] for loop in _reference(pcb)]


def _reference(pcb):
    board, _, _ = extract(pcb, copper_layers=(), extra_layers=())
    loops = [list(board.exterior.coords)] if board else []
    for fp in children(pcb, 'footprint'):
        ref = next((p[2] for p in children(fp, 'property') if p[1] == 'Reference'), '')
        fp_at = at_of(fp)
        if re.match(r'^SW\d+$', ref):
            if 'SW-SMD' in fp[1]:  # 6 x 6 mm tact switch body
                body = [place(p, fp_at) for p in [(-3, -3), (3, -3), (3, 3), (-3, 3), (-3, -3)]]
                loops.append(body)
            for pad in children(fp, 'pad'):
                geom, _ = pad_shape(pad, fp_at)
                loops.append(list(geom.exterior.coords))
        elif re.match(r'^LED\d+$', ref):
            loops.append([place(p, fp_at) for p in [(-1, -1), (1, -1), (1, 1), (-1, 1), (-1, -1)]])
    return loops


# ---------- FeatureScript output ----------

def polys(geom):
    if geom is None or geom.is_empty:
        return []
    if geom.geom_type == 'Polygon':
        return [geom]
    return [g for g in getattr(geom, 'geoms', []) if g.geom_type == 'Polygon']


def fs_loops(rings, origin, simplify=0.01):
    out = []
    for ring in rings:
        line = LineString(ring).simplify(simplify)
        pts = [(x - origin[0], -(y - origin[1])) for x, y in line.coords]
        if len(pts) < 3:
            continue
        if pts[0] != pts[-1]:
            pts.append(pts[0])
        out.append('[' + ', '.join(f'[{x:.3f}, {y:.3f}]' for x, y in pts) + ']')
    return '[\n    ' + ',\n    '.join(out) + '\n]' if out else '[]'


def rings_of(geom):
    outer, inner = [], []
    for p in polys(geom):
        outer.append(list(p.exterior.coords))
        inner.extend(list(i.coords) for i in p.interiors)
    return outer, inner


TEMPLATE = r'''FeatureScript %(version)s;
import(path : "onshape/std/geometry.fs", version : "%(version)s.0");
// ^ If Onshape complains about the version, replace the two lines above with the
//   two lines a fresh Feature Studio tab generates.
// Generated by tools/kicad2fs.py from %(source)s. Units: mm. Back face at Z = 0, top at Z = thickness.

const BOARD_OUTER = %(board_outer)s;
const BOARD_CUTOUTS = %(board_inner)s;
const FCU_OUTER = %(fcu_outer)s;
const FCU_INNER = %(fcu_inner)s;
const BCU_OUTER = %(bcu_outer)s;
const BCU_INNER = %(bcu_inner)s;
const POCKETS = %(pockets)s;
const HOLES = %(holes)s; // [x, y, diameter]
const BADGE_REF = %(ref)s;

function loopSketch(context is Context, id is Id, z is ValueWithUnits, loops is array)
{
    var sk = newSketchOnPlane(context, id, {
            "sketchPlane" : plane(vector(0 * millimeter, 0 * millimeter, z), vector(0, 0, 1), vector(1, 0, 0)) });
    for (var i = 0; i < size(loops); i += 1)
    {
        var pts = mapArray(loops[i], function(p) { return vector(p[0], p[1]) * millimeter; });
        skPolyline(sk, "loop" ~ i, { "points" : pts });
    }
    skSolve(sk);
}

function prism(context is Context, id is Id, zStart is ValueWithUnits, depth is ValueWithUnits, loops is array)
{
    loopSketch(context, id + "sk", zStart, loops);
    opExtrude(context, id + "ex", {
            "entities" : qSketchRegion(id + "sk"),
            "direction" : vector(0, 0, 1),
            "endBound" : BoundingType.BLIND,
            "endDepth" : depth });
    return qCreatedBy(id + "ex", EntityType.BODY);
}

function cut(context is Context, id is Id, targets is Query, tools is Query)
{
    opBoolean(context, id, { "tools" : tools, "targets" : targets, "operationType" : BooleanOperationType.SUBTRACTION });
}

annotation { "Feature Type Name" : "KiCad board" }
export const kicadBoard = defineFeature(function(context is Context, id is Id, definition is map)
    precondition
    {
        annotation { "Name" : "Board thickness" }
        isLength(definition.thickness, { (millimeter) : [0.4, 2.0, 50] } as LengthBoundSpec);
        annotation { "Name" : "Top copper (feather) height" }
        isLength(definition.featherHeight, { (millimeter) : [0.1, 4.0, 50] } as LengthBoundSpec);
        annotation { "Name" : "Pocket depth (User.1)" }
        isLength(definition.pocketDepth, { (millimeter) : [0.1, 1.0, 50] } as LengthBoundSpec);
        annotation { "Name" : "Hole diameter offset" }
        isLength(definition.holeOffset, { (millimeter) : [-1, 0.0, 1] } as LengthBoundSpec);
        annotation { "Name" : "Emboss back copper", "Default" : false }
        definition.embossBack is boolean;
        if (definition.embossBack)
        {
            annotation { "Name" : "Back copper relief" }
            isLength(definition.backRelief, { (millimeter) : [0.1, 0.6, 5] } as LengthBoundSpec);
        }
        annotation { "Name" : "Badge reference sketch", "Default" : true }
        definition.showRef is boolean;
        if (definition.showRef)
        {
            annotation { "Name" : "Gap to badge face" }
            isLength(definition.badgeGap, { (millimeter) : [0, 5.5, 50] } as LengthBoundSpec);
        }
    }
    {
        const t = definition.thickness;
        const big = 200 * millimeter;
        var bodies = [];

        // board plate and its cut-outs
        var board = prism(context, id + "board", 0 * millimeter, t, BOARD_OUTER);
        bodies = append(bodies, board);
        if (size(BOARD_CUTOUTS) > 0)
        {
            cut(context, id + "cutoutsCut", board, prism(context, id + "cutouts", -big / 2, big, BOARD_CUTOUTS));
        }

        // pockets in the top face
        if (size(POCKETS) > 0)
        {
            cut(context, id + "pocketsCut", board, prism(context, id + "pockets", t - definition.pocketDepth, big, POCKETS));
        }

        // raised top copper (feathers)
        if (size(FCU_OUTER) > 0)
        {
            var fcu = prism(context, id + "fcu", t, definition.featherHeight, FCU_OUTER);
            bodies = append(bodies, fcu);
            if (size(FCU_INNER) > 0)
            {
                cut(context, id + "fcuInnerCut", fcu, prism(context, id + "fcuInner", t, big, FCU_INNER));
            }
        }

        // back copper: sketch always, emboss optionally
        if (size(BCU_OUTER) > 0)
        {
            if (definition.embossBack)
            {
                var bcu = prism(context, id + "bcu", -definition.backRelief, definition.backRelief, BCU_OUTER);
                bodies = append(bodies, bcu);
                if (size(BCU_INNER) > 0)
                {
                    cut(context, id + "bcuInnerCut", bcu, prism(context, id + "bcuInner", -big, big, BCU_INNER));
                }
            }
            else
            {
                loopSketch(context, id + "bcuSketch", 0 * millimeter, concatenateArrays([BCU_OUTER, BCU_INNER]));
            }
        }

        // through holes
        if (size(HOLES) > 0)
        {
            var sk = newSketchOnPlane(context, id + "holesSk", {
                    "sketchPlane" : plane(vector(0 * millimeter, 0 * millimeter, -big / 2), vector(0, 0, 1), vector(1, 0, 0)) });
            for (var i = 0; i < size(HOLES); i += 1)
            {
                skCircle(sk, "hole" ~ i, {
                        "center" : vector(HOLES[i][0], HOLES[i][1]) * millimeter,
                        "radius" : (HOLES[i][2] * millimeter + definition.holeOffset) / 2 });
            }
            skSolve(sk);
            opExtrude(context, id + "holesEx", {
                    "entities" : qSketchRegion(id + "holesSk"),
                    "direction" : vector(0, 0, 1),
                    "endBound" : BoundingType.BLIND,
                    "endDepth" : big });
            cut(context, id + "holesCut", qUnion(bodies), qCreatedBy(id + "holesEx", EntityType.BODY));
        }

        if (size(bodies) > 1)
        {
            opBoolean(context, id + "merge", { "tools" : qUnion(bodies), "operationType" : BooleanOperationType.UNION });
        }

        // badge front face, for fitting the dock by hand
        if (definition.showRef && size(BADGE_REF) > 0)
        {
            loopSketch(context, id + "badgeRef", -definition.badgeGap, BADGE_REF);
        }
    });
'''


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('pcb')
    ap.add_argument('-o', '--out', default=None)
    ap.add_argument('--ref', help='badge .kicad_pcb to include as a reference sketch')
    ap.add_argument('--origin', nargs=2, type=float, default=[0.0, 0.0], metavar=('X', 'Y'),
                    help='KiCad point that becomes the Onshape origin')
    ap.add_argument('--ref-turns', type=int, default=0,
                    help='quarter turns applied to the badge reference (must match make_goose_template.py)')
    ap.add_argument('--fs-version', default='2384')
    args = ap.parse_args()

    pcb = parse_sexpr(open(args.pcb, encoding='utf8').read())
    board, layers, holes = extract(pcb)
    if board is None:
        raise SystemExit('No closed outline found on Edge.Cuts')

    # copper and pockets only exist where there is board
    fcu = layers['F.Cu'].intersection(board) if layers['F.Cu'] else None
    bcu = layers['B.Cu'].intersection(board) if layers['B.Cu'] else None
    pockets = layers['User.1']

    o = args.origin
    fcu_o, fcu_i = rings_of(fcu)
    bcu_o, bcu_i = rings_of(bcu)
    ref_loops = reference(parse_sexpr(open(args.ref, encoding='utf8').read()), args.ref_turns) if args.ref else []
    holes_fs = '[' + ', '.join(f'[{x - o[0]:.3f}, {-(y - o[1]):.3f}, {d:.3f}]' for x, y, d in holes) + ']'

    text = TEMPLATE % {
        'version': args.fs_version,
        'source': args.pcb.replace('\\', '/'),
        'board_outer': fs_loops([list(board.exterior.coords)], o),
        'board_inner': fs_loops([list(i.coords) for i in board.interiors], o),
        'fcu_outer': fs_loops(fcu_o, o), 'fcu_inner': fs_loops(fcu_i, o),
        'bcu_outer': fs_loops(bcu_o, o), 'bcu_inner': fs_loops(bcu_i, o),
        'pockets': fs_loops(rings_of(pockets)[0], o),
        'holes': holes_fs,
        'ref': fs_loops(ref_loops, o),
    }
    out = args.out or re.sub(r'\.kicad_pcb$', '', args.pcb) + '.fs'
    open(out, 'w', encoding='utf8').write(text)
    minx, miny, maxx, maxy = board.bounds
    print(f'{out}: board {maxx - minx:.1f} x {maxy - miny:.1f} mm, {len(board.interiors)} cut-outs, '
          f'{len(fcu_o)} top islands, {len(bcu_o)} back copper shapes, {len(holes)} holes, {len(ref_loops)} ref loops')


if __name__ == '__main__':
    main()
