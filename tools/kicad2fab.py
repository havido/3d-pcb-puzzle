"""KiCad board -> Onshape FeatureScript for the full 3DPCB fabrication set.

Bodies, modelled in their assembled positions (Z = 0 is the board's back face):
  board     plate + raised traces + moat and shear rim around every trace + holes
  cutter    press plate: grooves over the traces, teeth that enter the moats, alignment pins, pry scoops
  tray      holds the badge under the board: lips, walls, dowels (clamshell) or edge locators + spring finger (slide), lock posts
  keys      slide through the lock posts to hold the board on the tray
  clip      C-clip over the board edge and the tray bottom (third hold-down)
  plungerN  captive button caps for --open buttons
  pinGauge  sets how far the pogo pins stick out of the board back
  shim      (slide style only) two strips pushed in under the badge to lift it onto the pogo pins

All XY fits are baked in here (edit P below and re-run); the FeatureScript only extrudes.
Tolerances follow the Bambu A1 mini guide in CLAUDE.md. How it works: docs/PIPELINE.md.

Usage:
  python tools/kicad2fab.py goose/goose_landscape_v3.kicad_pcb --badge "Archive 2/badge.kicad_pcb" --turns 1 --open SW6 SW7
"""
import argparse
import math
import re
from types import SimpleNamespace

from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import transform, unary_union
from shapely import affinity

from kicad2fs import at_of, child, children, extract, layers_of, parse_sexpr, polys, reference, rotate_pt, xy

P = SimpleNamespace(
    # board
    PLATE_T=4.0,          # plate thickness. 4.0 because the lock posts only fit at the tail end: the plate cantilevers ~58 mm over the pogo pins (2.4 mm would bow ~1 mm under 4 N, 4.0 mm ~0.2 mm)
    TRACE_H=1.0,          # raised trace height above the plate top (5 layers at 0.2)
    MOAT_W=1.5,           # moat around every trace = side gap + tooth + shear gap
    MOAT_D=0.6,           # moat depth below the plate top
    RIM_W=0.8,            # shear rim outside the moat (2 extrusion lines)
    RIM_H=0.4,            # rim height above the plate top (2 layers)
    BACK_RECESS_D=0.4,    # recess for back copper tape so the board sits flat on the tray
    BACK_RECESS_CL=0.25,  # recess is this much wider than the track, per side
    # copper tape + cutter
    TAPE_T=0.10,          # worst-case tape thickness
    SIDE_CL=0.10,         # cutter to tape on the trace sidewalls (groove = trace + 2 x (TAPE_T + SIDE_CL))
    TOP_CL=0.05,          # cutter to tape on the trace top (cutter bottoms out here)
    SHEAR_CL=0.10,        # tooth to rim edge: the shearing gap. THE number to tune on a coupon.
    TOOTH_FLOOR_CL=0.2,   # tooth tip to moat floor
    CUTTER_T=4.0,
    PRY_R=9.0,            # pry scoop radius
    PRY_D=1.6,            # pry scoop depth into the cutter face
    # holes
    POGO_HOLE=1.18,       # press fit for a 1.02 mm P75 pin
    VIA_HOLE=2.4,         # prints ~2.2: M2 screw, wire, or a tape tail
    PIN_D=5.0,            # cutter alignment pins
    SOCKET_D=5.2,
    # tray-to-board lock: posts on the tray pass through the board, a key slides through each post (no glue)
    POST_D=6.0,
    POST_HOLE_D=6.2,      # locating fit
    BOSS_D=10.0,          # raised ring on the board around each post hole; the key bears on it, above the traces
    KEY_W=2.2,            # key in a 2.4 mm slot
    KEY_SLOT_W=2.4,
    KEY_T=1.8,            # key in a 2.0 mm tall slot
    KEY_SLOT_H=2.0,
    KEY_LEN=16.0,
    POST_CAP=1.2,
    EAR_REACH=7.0,        # how far outside the tray box a post may sit (joined to the wall by an ear)
    # edge clip: a C-clip slid over the board edge and the tray bottom, near the pogo pins (third hold-down)
    CLIP_W=10.0,
    CLIP_T=2.5,
    CLIP_REACH=2.0,       # how far each jaw reaches in from the edge (the v3 goose only has ~2.4 mm of bare margin)
    CLIP_CL=0.1,          # clip opening minus the stack it grips
    # clamshell style: badge drops onto two dowels through its corner holes
    DOWEL_CL=0.15,        # diametral clearance in the badge hole (snug)
    DOWEL_FLAT=2.4,       # length of the relieved (diamond) dowel along the line between the dowels
    DOWEL_BOSS_R=5.5,
    SOCKET_CB=0.5,        # counterbore at the socket mouth (elephant foot + lead-in)
    # badge slot
    GAP=5.5,              # board back face to badge front face (tact switches are 5.0 tall)
    PCB_T=1.6,
    PCB_T_MAX=1.76,
    PCB_SIDE_CL=0.30,     # drop-in clearance per side
    SHIM_T=1.9,           # lifts the badge onto the pins after it has slid in
    LIP_W=3.0,            # lip under the badge back
    LIP_T=2.0,
    WALL_W=5.0,
    TRAY_START_Y=118.0,   # portrait badge Y where the rails start (badge bottom edge is 177.3)
    LOCATOR_Y=(122.0, 156.0),   # two pads on the badge's left long edge (portrait Y)
    LOCATOR_LEN=4.0,
    SPRING_Y=(138.0, 159.0),    # spring finger on the right long edge (portrait Y): fixed end first
    SPRING_T=1.5,
    SPRING_SLIT=1.0,
    SPRING_PRELOAD=0.4,   # bump interference with the badge edge
    OPEN_BUTTON_D=13.0,   # hole over a button that must stay pressable
    # badge buttons (KH-6X6X5H tact switches: 6 x 6 body ~3.5 tall, 3.5 mm round actuator, 5.0 tall overall)
    BUTTON_H=5.0,
    ACTUATOR_POCKET_D=5.0,     # relief in the board back over every covered button: clears the actuator, misses the pogo holes
    ACTUATOR_POCKET_DEPTH=1.0, # covered buttons end up with GAP - BUTTON_H + this = 1.5 mm of air, so the board can never press them
    PLUNGER_CL=0.3,            # plunger stem to hole, per side
    PLUNGER_FLANGE=1.5,        # flange radius beyond the stem: keeps the plunger captive under the board
    PLUNGER_PROUD=1.0,         # plunger top above the trace tops
    PAD_H=0.5,                 # switch lead + solder above the badge face, where the pogo tip lands
    POGO_TRAVEL=1.2,           # target pogo compression when assembled
)
PINS_PORTRAIT = [(73.8, 123.4), (67.0, 131.0), (89.6, 131.0), (83.5, 134.2)]  # pogo positions (see make_goose_template.py)
RES = 8  # buffer resolution (segments per quarter circle)


def rot(geom, turns):
    return transform(lambda xs, ys: tuple(zip(*[rotate_pt((x, y), turns) for x, y in zip(xs, ys)])), geom)


def clean(geom, min_area=0.3):
    geom = geom.buffer(0)
    out = []
    for p in polys(geom):
        if p.area < min_area:
            continue
        holes = [h for h in p.interiors if Polygon(h).area >= min_area]
        out.append(Polygon(p.exterior, holes))
    return unary_union(out) if out else Polygon()


STEP = 0.03  # walls that would otherwise be flush are offset by this much on purpose: near-coincident faces break booleans
EPS = 0.05  # bodies overlap by this much so unions are volumes, never bare face/edge/point contacts


def solidify(geom, e=0.06):
    """Remove the 2D conditions that make non-manifold solids: point contacts, zero-width necks, hairline gaps."""
    return geom.buffer(e, RES).buffer(-2 * e, RES).buffer(e, RES)


def copper_by_net(pcb, layer):
    nets = {n[1]: n[2] for n in children(pcb, 'net')}
    out = {}
    for s in children(pcb, 'segment'):
        if layers_of(s)[0] == layer:
            g = LineString([xy(child(s, 'start')), xy(child(s, 'end'))]).buffer(float(child(s, 'width')[1]) / 2, RES)
            out.setdefault(nets.get(child(s, 'net')[1], ''), []).append(g)
    vias = []
    for v in children(pcb, 'via'):
        x, y = xy(child(v, 'at'))
        net = nets.get(child(v, 'net')[1], '')
        out.setdefault(net, []).append(Point(x, y).buffer(float(child(v, 'size')[1]) / 2, RES))
        vias.append((x, y))
    return {k: unary_union(v) for k, v in out.items()}, vias


def farthest_points(region, n, step=2.0):
    """Greedy pick of n well-spread points inside region."""
    minx, miny, maxx, maxy = region.bounds
    cands = [Point(minx + i * step, miny + j * step)
             for i in range(int((maxx - minx) / step) + 1) for j in range(int((maxy - miny) / step) + 1)]
    cands = [c for c in cands if region.contains(c)]
    if len(cands) < n:
        raise SystemExit(f'Not enough free room for {n} alignment features')
    chosen = [min(cands, key=lambda c: (c.x, c.y))]
    while len(chosen) < n:
        chosen.append(max(cands, key=lambda c: min(c.distance(k) for k in chosen)))
    return [(c.x, c.y) for c in chosen]


def edge_x(badge, y, side):
    """X of the badge outline at portrait height y on the 'left' or 'right' edge."""
    hit = badge.intersection(LineString([(0, y), (300, y)]))
    return hit.bounds[0] if side == 'left' else hit.bounds[2]


def build_tray(badge, style):
    """Portrait badge coordinates; the badge's bottom end sits in the tray.
    slide: badge slides in along +Y, 2 + 1 edge locators + spring finger, shims lift it onto the pins.
    clamshell: badge drops onto a round + a relieved dowel through its two bottom corner holes."""
    minx, miny, maxx, maxy = badge.bounds
    solid = Polygon(badge.exterior)
    tray_box = box(minx - P.WALL_W, P.TRAY_START_Y, maxx + P.WALL_W, maxy + P.WALL_W)
    clip = box(minx - 50, P.TRAY_START_Y - 1, maxx + 50, maxy + 50)
    grown = solid.buffer(P.PCB_SIDE_CL, RES)
    dowels, shims = [], Polygon()

    if style == 'slide':
        travel = maxy - P.TRAY_START_Y + 5
        swept = unary_union([affinity.translate(grown, 0, -i * 0.5) for i in range(int(travel / 0.5) + 1)])
        cavity = swept.intersection(clip)
        pads = []
        for y in P.LOCATOR_Y:
            x = edge_x(solid, y, 'left')
            pads.append(box(x - 1.0, y - P.LOCATOR_LEN / 2, x + 0.5, y + P.LOCATOR_LEN / 2))
        cx = (minx + maxx) / 2
        pads.append(box(cx - P.LOCATOR_LEN / 2, maxy - 0.5, cx + P.LOCATOR_LEN / 2, maxy + 1.0))
        cavity = cavity.difference(unary_union(pads).difference(solid))
        walls = tray_box.difference(cavity)

        y0, y1 = P.SPRING_Y
        xe = max(edge_x(solid, y, 'right') for y in (y0, (y0 + y1) / 2, y1))
        xw = xe + P.PCB_SIDE_CL
        slit = box(xw + P.SPRING_T, y0, xw + P.SPRING_T + P.SPRING_SLIT, y1)
        free_cut = box(xw - P.LIP_W - 1, y1 - P.SPRING_SLIT, xw + P.SPRING_T + P.SPRING_SLIT, y1)
        yb = y1 - 6.0
        xin = edge_x(solid, yb, 'right') - P.SPRING_PRELOAD
        bump = Polygon([(xw + 0.2, yb - 5), (xin, yb - 2), (xin, yb + 2), (xw + 0.2, yb + 3.5)])
        walls = walls.difference(slit).difference(free_cut).union(bump.difference(free_cut))
        no_go = box(xw - 1, y0 - 3, xw + 50, y1 + 3)          # keep posts off the spring

        lips = cavity.difference(swept.buffer(-P.LIP_W, RES)).intersection(tray_box)
        lips = lips.difference(box(xw - P.LIP_W - 1, y0 - 1, xw + 1, y1 + 1))

        parts = []
        for side, sign in (('left', 1), ('right', -1)):
            xs = [edge_x(solid, y, side) for y in range(int(P.SPRING_Y[0]), int(maxy) - 16, 4)]
            edge = max(xs) if side == 'left' else min(xs)
            inner, outer = edge + sign * (P.LIP_W - 0.3), edge + sign * 0.6
            strip = box(min(inner, outer), P.TRAY_START_Y - 14, max(inner, outer), maxy - 16)
            tab = box(min(edge - sign * 7, inner), P.TRAY_START_Y - 14, max(edge - sign * 7, inner), P.TRAY_START_Y - 3)
            parts.append(strip.union(tab))
        shims = unary_union(parts)
    else:
        cavity = grown.intersection(clip)
        walls = tray_box.difference(cavity)
        no_go = Polygon()
        lips = cavity.difference(grown.buffer(-P.LIP_W, RES)).intersection(tray_box)
        holes = [Polygon(i) for i in badge.interiors if tray_box.contains(Polygon(i).centroid)]
        if len(holes) < 2:
            raise SystemExit('clamshell needs two badge holes inside the tray')
        holes = sorted(holes, key=lambda h: h.centroid.x)[:2]
        (ax, ay), (bx, by) = [(h.centroid.x, h.centroid.y) for h in holes]
        ang = math.degrees(math.atan2(by - ay, bx - ax))
        for k, h in enumerate(holes):
            d = (h.bounds[2] - h.bounds[0]) - P.DOWEL_CL
            pin = h.centroid.buffer(d / 2, 16)
            if k == 1:   # relieved dowel: only stops rotation, so hole-spacing error cannot bind
                c = h.centroid
                slab = affinity.rotate(box(c.x - P.DOWEL_FLAT / 2, c.y - d, c.x + P.DOWEL_FLAT / 2, c.y + d), ang, origin=c)
                pin = pin.intersection(slab)
            dowels.append(pin)
            lips = lips.union(h.centroid.buffer(P.DOWEL_BOSS_R, RES).intersection(cavity))
    return SimpleNamespace(walls=walls, lips=lips, shims=shims, box=tray_box, cavity=cavity, dowels=dowels, no_go=no_go)


def place_posts(region):
    """Two post centres, as far apart as the free area allows."""
    minx, miny, maxx, maxy = region.bounds
    grid = [Point(minx + i * 1.0, miny + j * 1.0) for i in range(int(maxx - minx) + 1) for j in range(int(maxy - miny) + 1)]
    grid = [g for g in grid if region.contains(g)]
    if len(grid) < 2:
        raise SystemExit('No room for two locking posts: free some plate area over the tray walls')
    a = grid[0]
    for _ in range(3):   # farthest-pair by iteration
        b = max(grid, key=lambda g: g.distance(a))
        a = max(grid, key=lambda g: g.distance(b))
    if a.distance(b) < P.BOSS_D + 4:
        raise SystemExit('Locking posts would collide: free more plate area over the tray walls')
    return [(a.x, a.y), (b.x, b.y)]


def place_clip(plate, walls, keepout, score):
    """Point on the board edge, over a tray wall, clear of copper, with the lowest score(point). Returns (point, outward normal)."""
    ring = plate.exterior
    best = None
    for s in range(0, int(ring.length)):
        pt = ring.interpolate(s)
        if walls.distance(pt) > 1.5 or keepout.distance(pt) < P.CLIP_REACH + 0.3:
            continue
        a, b = ring.interpolate(s - P.CLIP_W / 2), ring.interpolate(s + P.CLIP_W / 2)
        if LineString([a, b]).distance(pt) > 0.4:      # needs a straight stretch of edge
            continue
        if best is None or score(pt) < score(best[0]):
            tx, ty = (b.x - a.x), (b.y - a.y)
            n = math.hypot(tx, ty)
            nx, ny = ty / n, -tx / n
            if plate.contains(Point(pt.x + nx, pt.y + ny)):
                nx, ny = -nx, -ny
            best = (pt, (nx, ny))
    return best


def clip_rect(pt, normal, n0, n1):
    """Rectangle CLIP_W wide along the edge, from n0 to n1 along the outward normal."""
    nx, ny = normal
    tx, ty = -ny, nx
    h = P.CLIP_W / 2
    return Polygon([(pt.x + tx * u + nx * v, pt.y + ty * u + ny * v) for u, v in ((-h, n0), (h, n0), (h, n1), (-h, n1))])


def ring_pts(ring, origin):
    line = LineString(ring).simplify(0.01)
    pts = [(round(x - origin[0], 3), round(-(y - origin[1]), 3)) for x, y in line.coords]
    dedup = [pts[0]]
    for p in pts[1:]:
        if p != dedup[-1]:
            dedup.append(p)
    if dedup[0] != dedup[-1]:
        dedup.append(dedup[0])
    return '[' + ', '.join(f'[{x}, {y}]' for x, y in dedup) + ']' if len(dedup) >= 4 else None


class Ops:
    def __init__(self, origin):
        self.items, self.origin = [], origin

    def add(self, name, body, op, z0, z1, geom=None, circles=()):
        plist = []
        parts = polys(clean(geom)) if geom is not None else []
        for i in range(len(parts)):          # self-check: anything that would make a non-manifold solid
            if not parts[i].is_valid:
                print(f'  ! {body}/{name}: invalid polygon')
            for j in range(i + 1, len(parts)):
                if parts[i].distance(parts[j]) < 1e-6:
                    print(f'  ! {body}/{name}: two regions touch')
        for p in parts:
            outer = ring_pts(p.exterior.coords, self.origin)
            if outer:
                inner = [r for r in (ring_pts(i.coords, self.origin) for i in p.interiors) if r]
                plist.append(f'[{outer}, [{", ".join(inner)}]]')
        clist = [f'[{x - self.origin[0]:.3f}, {-(y - self.origin[1]):.3f}, {d:.3f}]' for x, y, d in circles]
        if not plist and not clist:
            return
        self.items.append(
            f'    {{ "name" : "{name}", "body" : "{body}", "op" : "{op}", "z0" : {z0:.3f}, "z1" : {z1:.3f},\n'
            f'      "polys" : [{", ".join(plist)}],\n      "circles" : [{", ".join(clist)}] }}')

    def pins(self, name, body, z0, z1, centres, d, up=True):
        """Alignment pins with a stepped lead-in at the tip (z1 end if up, z0 end if not)."""
        step = min(0.4, (z1 - z0) / 4)
        if up:
            self.add(name, body, 'add', z0, z1 - 2 * step, circles=[(x, y, d) for x, y in centres])
            self.add(name + 'Tip1', body, 'add', z1 - 2 * step - EPS, z1 - step, circles=[(x, y, d - 0.8) for x, y in centres])
            self.add(name + 'Tip2', body, 'add', z1 - step - EPS, z1, circles=[(x, y, d - 1.6) for x, y in centres])
        else:
            self.add(name, body, 'add', z0 + 2 * step, z1, circles=[(x, y, d) for x, y in centres])
            self.add(name + 'Tip1', body, 'add', z0 + step, z0 + 2 * step + EPS, circles=[(x, y, d - 0.8) for x, y in centres])
            self.add(name + 'Tip2', body, 'add', z0, z0 + step + EPS, circles=[(x, y, d - 1.6) for x, y in centres])


TEMPLATE = r'''FeatureScript %(version)s;
import(path : "onshape/std/geometry.fs", version : "%(version)s.0");
// ^ If Onshape complains about the version, replace the two lines above with the
//   two lines a fresh Feature Studio tab generates.
// Generated by tools/kicad2fab.py from %(source)s. Units: mm. Z = 0 is the board's back face.
// Bodies: see the "body" field of each op. "add" ops are unioned per body, "cut" ops are subtracted in order.

const OPS = [
%(ops)s
];
const MERGE = %(merge)s;
const BADGE_REF = %(ref)s;
const BADGE_Z = %(badge_z).3f;

function polySketch(context is Context, id is Id, z is ValueWithUnits, loops is array)
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

function extrudeSketch(context is Context, id is Id, sketchId is Id, depth is ValueWithUnits) returns Query
{
    opExtrude(context, id, {
            "entities" : qSketchRegion(sketchId),
            "direction" : vector(0, 0, 1),
            "endBound" : BoundingType.BLIND,
            "endDepth" : depth });
    return qCreatedBy(id, EntityType.BODY);
}

// one solid per polygon (outer loop minus its own inner loops), plus one solid per circle
function opSolids(context is Context, id is Id, op is map, z is ValueWithUnits, depth is ValueWithUnits) returns array
{
    var solids = [];
    for (var i = 0; i < size(op.polys); i += 1)
    {
        const pid = id + ("p" ~ i);
        polySketch(context, pid + "sk", z, [op.polys[i][0]]);
        var solid = extrudeSketch(context, pid + "ex", pid + "sk", depth);
        if (size(op.polys[i][1]) > 0)
        {
            polySketch(context, pid + "hsk", z, op.polys[i][1]);
            opBoolean(context, pid + "hcut", {
                    "tools" : extrudeSketch(context, pid + "hex", pid + "hsk", depth),
                    "targets" : solid,
                    "operationType" : BooleanOperationType.SUBTRACTION });
        }
        solids = append(solids, solid);
    }
    for (var i = 0; i < size(op.circles); i += 1)
    {
        const cid = id + ("c" ~ i);
        var sk = newSketchOnPlane(context, cid + "sk", {
                "sketchPlane" : plane(vector(0 * millimeter, 0 * millimeter, z), vector(0, 0, 1), vector(1, 0, 0)) });
        skCircle(sk, "c", {
                "center" : vector(op.circles[i][0], op.circles[i][1]) * millimeter,
                "radius" : op.circles[i][2] / 2 * millimeter });
        skSolve(sk);
        solids = append(solids, extrudeSketch(context, cid + "ex", cid + "sk", depth));
    }
    return solids;
}

annotation { "Feature Type Name" : "%(feature_title)s" }
export const %(feature_id)s = defineFeature(function(context is Context, id is Id, definition is map)
    precondition
    {
        annotation { "Name" : "Board", "Default" : true }
        definition.board is boolean;
        annotation { "Name" : "Cutter", "Default" : true }
        definition.cutter is boolean;
        annotation { "Name" : "Tray", "Default" : true }
        definition.tray is boolean;
        annotation { "Name" : "Shim (slide style only)", "Default" : true }
        definition.shim is boolean;
        annotation { "Name" : "Lock keys", "Default" : true }
        definition.keys is boolean;
        annotation { "Name" : "Button plungers, pin gauge, edge clip", "Default" : true }
        definition.extras is boolean;
        annotation { "Name" : "Exploded view gap (0 = assembled)" }
        isLength(definition.explode, { (millimeter) : [0, 20, 200] } as LengthBoundSpec);
        annotation { "Name" : "Badge reference sketch", "Default" : true }
        definition.showRef is boolean;
    }
    {
        var lift = { "board" : 0 * millimeter, "cutter" : definition.explode,
                "tray" : -definition.explode, "shim" : -2 * definition.explode, "keys" : 2 * definition.explode };
        var wanted = { "board" : definition.board, "cutter" : definition.cutter,
                "tray" : definition.tray, "shim" : definition.shim, "keys" : definition.keys };
        var bodies = {};
        var bodyOps = {};
        for (var k = 0; k < size(OPS); k += 1)
        {
            const b = OPS[k].body;
            bodies[b] = [];
            bodyOps[b] = [];
            if (wanted[b] == undefined)
            {
                wanted[b] = definition.extras;          // plungers, pin gauge
                lift[b] = 3 * definition.explode;
            }
        }

        // pass 1: build every "add" piece
        for (var k = 0; k < size(OPS); k += 1)
        {
            const op = OPS[k];
            if (!wanted[op.body] || op.op != "add")
                continue;
            const solids = opSolids(context, id + ("op" ~ k), op,
                op.z0 * millimeter + lift[op.body], (op.z1 - op.z0) * millimeter);
            bodies[op.body] = concatenateArrays([bodies[op.body], solids]);
            for (var s = 0; s < size(solids); s += 1)
                bodyOps[op.body] = append(bodyOps[op.body], op.name);
        }

        // pass 2: merge each body, one piece at a time so a failure names the piece
        for (var name in MERGE)
        {
            for (var m = 1; m < size(bodies[name]); m += 1)
            {
                try
                {
                    opBoolean(context, id + ("merge" ~ name ~ m), {
                            "tools" : qUnion([bodies[name][0], bodies[name][m]]),
                            "operationType" : BooleanOperationType.UNION });
                }
                catch (error)
                {
                    throw regenError("3DPCB: merging piece " ~ m ~ " (" ~ bodyOps[name][m] ~ ") into '" ~ name ~ "' failed");
                }
            }
        }

        var skipped = [];
        // pass 3: cuts, on the merged bodies
        for (var k = 0; k < size(OPS); k += 1)
        {
            const op = OPS[k];
            if (!wanted[op.body] || op.op != "cut" || size(bodies[op.body]) == 0)
                continue;
            const solids = opSolids(context, id + ("op" ~ k), op,
                op.z0 * millimeter + lift[op.body], (op.z1 - op.z0) * millimeter);
            for (var s = 0; s < size(solids); s += 1)
            {
                try
                {
                    opBoolean(context, id + ("cut" ~ k ~ "_" ~ s), {
                            "tools" : solids[s],
                            "targets" : qUnion(bodies[op.body]),
                            "operationType" : BooleanOperationType.SUBTRACTION });
                }
                catch (error)
                {
                    skipped = append(skipped, op.name ~ " #" ~ s);
                    try
                    {
                        opDeleteBodies(context, id + ("cutDel" ~ k ~ "_" ~ s), { "entities" : solids[s] });
                    }
                    catch (error2)
                    {
                    }
                }
            }
        }

        if (size(skipped) > 0)
        {
            var msg = "3DPCB: these cuts were skipped (the rest of the model is complete): ";
            for (var s = 0; s < size(skipped); s += 1)
                msg = msg ~ skipped[s] ~ "; ";
            reportFeatureWarning(context, id, msg);
        }

        if (definition.showRef && size(BADGE_REF) > 0)
        {
            polySketch(context, id + "badgeRef", BADGE_Z * millimeter - definition.explode, BADGE_REF);
        }
    });
'''


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('pcb')
    ap.add_argument('-o', '--out')
    ap.add_argument('--badge', required=True, help='badge .kicad_pcb')
    ap.add_argument('--turns', type=int, default=0, help='quarter turns used by make_goose_template.py')
    ap.add_argument('--style', choices=['slide', 'clamshell'], default='clamshell')
    ap.add_argument('--open', nargs='*', default=[], metavar='SWn', help='badge buttons that need a finger hole')
    ap.add_argument('--origin', nargs=2, type=float, default=[0.0, 0.0])
    ap.add_argument('--fs-version', default='2384')
    ap.add_argument('--preview', help='write a PNG preview here')
    args = ap.parse_args()

    pcb = parse_sexpr(open(args.pcb, encoding='utf8').read())
    badge_pcb = parse_sexpr(open(args.badge, encoding='utf8').read())
    plate, _, _ = extract(pcb)
    if plate is None:
        raise SystemExit('No closed outline found on Edge.Cuts')
    badge_board, _, _ = extract(badge_pcb, copper_layers=(), extra_layers=())
    badge = badge_board

    switches = {}
    for fp in children(badge_pcb, 'footprint'):
        ref = next((p[2] for p in children(fp, 'property') if p[1] == 'Reference'), '')
        if re.match(r'^SW\d+$', ref) and 'SW-SMD' in fp[1]:
            switches[ref] = at_of(fp)[:2]

    # ----- board copper features -----
    fnets, vias = copper_by_net(pcb, 'F.Cu')
    bnets, _ = copper_by_net(pcb, 'B.Cu')
    inside = plate.buffer(-0.8)
    cu = solidify(unary_union(list(fnets.values())).intersection(inside)).simplify(0.01)
    moat_outer = cu.buffer(P.MOAT_W, RES)
    moat = solidify(moat_outer.difference(cu).intersection(inside))
    moat_outer = moat.union(cu)
    rim = solidify(cu.buffer(P.MOAT_W + P.RIM_W, RES).intersection(inside).difference(moat_outer.buffer(0.001)))
    groove = cu.buffer(P.TAPE_T + P.SIDE_CL, RES)
    teeth = solidify(moat_outer.buffer(-P.SHEAR_CL, RES).difference(groove).intersection(inside)).difference(groove.buffer(STEP, RES))
    teeth = solidify(teeth)
    plate_top = solidify(plate.difference(moat.buffer(-STEP, RES)))
    cutter_face = solidify(plate.difference(groove))
    bcu = unary_union(list(bnets.values())) if bnets else Polygon()
    # vias also have a pad on the back; only real back tracks get a recess
    back_tracks = unary_union([LineString([xy(child(s, 'start')), xy(child(s, 'end'))]).buffer(float(child(s, 'width')[1]) / 2 + P.BACK_RECESS_CL, RES)
                               for s in children(pcb, 'segment') if layers_of(s)[0] == 'B.Cu'] or [Polygon()])

    # places where two DIFFERENT nets share one moat: tape is not sheared there
    shared = []
    names = list(fnets)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = fnets[names[i]], fnets[names[j]]
            if a.distance(b) < 2 * (P.MOAT_W + P.RIM_W):
                zone = a.buffer(P.MOAT_W + P.RIM_W).intersection(b.buffer(P.MOAT_W + P.RIM_W))
                for z in polys(zone):
                    c = z.centroid
                    shared.append((names[i] or 'no-net', names[j] or 'no-net', round(c.x, 1), round(c.y, 1), round(a.distance(b), 2)))

    pogo = [rotate_pt(p, args.turns) for p in PINS_PORTRAIT]
    is_pogo = lambda v: any(math.dist(v, q) < 0.3 for q in pogo)
    pogo_holes = [(x, y, P.POGO_HOLE) for x, y in vias if is_pogo((x, y))]
    via_holes = [(x, y, P.VIA_HOLE) for x, y in vias if not is_pogo((x, y))]

    # ----- tray (portrait) -> board frame -----
    tray = build_tray(badge, args.style)
    walls, lips, shims, tray_box, cavity, no_go = (rot(g, args.turns) for g in (tray.walls, tray.lips, tray.shims, tray.box, tray.cavity, tray.no_go))
    dowels = [rot(d, args.turns) for d in tray.dowels]

    keepout = unary_union([cu.buffer(P.MOAT_W + P.RIM_W + 1.0), bcu.buffer(1.5), back_tracks.buffer(1.0)])
    rb = P.BOSS_D / 2
    rh = P.POST_HOLE_D / 2 + 0.8                     # only the hole itself has to miss the copper features
    tight = cu.buffer(P.MOAT_W + P.RIM_W + 0.3)
    post_keepout = unary_union([tight, bcu.buffer(1.0), back_tracks.buffer(0.5)] + [Point(x, y).buffer(d / 2 + 1) for x, y, d in pogo_holes + via_holes])
    post_region = (plate.buffer(-(rh + 1.0)).intersection(tray_box.buffer(P.EAR_REACH))
                   .difference(post_keepout.buffer(rh)).difference(cavity.buffer(P.POST_D / 2 + 2.5)).difference(no_go.buffer(rh)))
    pogo_centre = Point(sum(p[0] for p in pogo) / len(pogo), sum(p[1] for p in pogo) / len(pogo))
    posts = place_posts(post_region)
    def axis_dist(pnt, a, b):
        return abs((b[0] - a[0]) * (pnt[1] - a[1]) - (b[1] - a[1]) * (pnt[0] - a[0])) / math.dist(a, b)

    def lever_at(pt):
        # lift at the pogo pins per mm of play: pins' distance from the clip-to-far-post axis over the near post's distance
        c = (pt.x, pt.y)
        far = max(posts, key=lambda q: math.dist(q, c))
        near = min(posts, key=lambda q: math.dist(q, c))
        return axis_dist((pogo_centre.x, pogo_centre.y), c, far) / max(axis_dist(near, c, far), 1e-6)

    clip = place_clip(plate, walls, cu.buffer(P.MOAT_W + P.RIM_W), lever_at)
    if clip is None:
        raise SystemExit('No straight, copper-free stretch of board edge over a tray wall for the edge clip')
    clip_pt, clip_n = clip
    # how far the tray wall sticks out past the board edge at the clip (negative = board overhangs the wall)
    probe = clip_rect(clip_pt, clip_n, -20, 20).intersection(walls)
    wall_out = max(((x - clip_pt.x) * clip_n[0] + (y - clip_pt.y) * clip_n[1]) for g in polys(probe) for x, y in g.exterior.coords)
    spine0 = max(0.0, wall_out) + 0.3
    lever = lever_at(clip_pt)
    ears = []
    for x, y in posts:
        c = Point(x, y)
        if not walls.buffer(-(P.POST_D / 2 + 1.5)).contains(c):
            near = tray_box.exterior.interpolate(tray_box.exterior.project(c))
            ears.append(LineString([c, near]).buffer(P.POST_D / 2 + 2.0, RES))
    walls = unary_union([walls] + ears).difference(cavity) if ears else walls
    # boss = whatever part of the ring fits between the copper features; key direction = where the boss is
    bosses, key_angles = [], []
    for x, y in posts:
        boss = Point(x, y).buffer(rb, RES).difference(tight).intersection(plate)
        boss = max(polys(boss), key=lambda g: g.area) if polys(boss) else Point(x, y).buffer(rh)
        foot = box(x - P.KEY_LEN / 2, y - P.KEY_W / 2, x + P.KEY_LEN / 2, y + P.KEY_W / 2)
        ang = max(range(0, 180, 10), key=lambda a: affinity.rotate(foot, a, origin=(x, y)).intersection(boss).area)
        bosses.append(boss)
        key_angles.append(ang)
    taken = unary_union([Point(p).buffer(rb + 3) for p in posts])
    r = P.SOCKET_D / 2
    cutter_pin_region = plate.buffer(-(r + 2.5)).difference(keepout.buffer(r)).difference(taken)
    cutter_pins = farthest_points(cutter_pin_region, 3, step=2.0)

    # finger holes over buttons that must stay pressable
    open_holes = []
    for ref in args.open:
        c = rotate_pt(switches[ref], args.turns)
        room = 2 * (keepout.distance(Point(c)) + 1.0 - 0.8)
        d = min(P.OPEN_BUTTON_D, room)
        open_holes.append((c[0], c[1], d))
        print(f'  finger hole over {ref}: {d:.1f} mm' + ('  <-- tight, move copper away if you can' if d < 10 else ''))

    # relief pockets over covered buttons
    solid_plate = Polygon(plate.exterior)
    open_refs = set(args.open)
    covered = {ref: rotate_pt(c, args.turns) for ref, c in switches.items()
               if ref not in open_refs and solid_plate.buffer(3).contains(Point(rotate_pt(c, args.turns)))}
    pockets = [(x, y, P.ACTUATOR_POCKET_D) for x, y in covered.values()]
    for ref, (x, y) in covered.items():
        near = min(math.dist((x, y), h[:2]) - h[2] / 2 for h in pogo_holes)
        if near < P.ACTUATOR_POCKET_D / 2 + 0.6:
            print(f'  ! pocket over {ref} comes within {near - P.ACTUATOR_POCKET_D / 2:.2f} mm of a pogo hole')

    # pry scoops: two boundary points far from copper and from each other
    ring = plate.exterior
    cands = [ring.interpolate(s) for s in range(0, int(ring.length), 3)]
    cands = [c for c in cands if keepout.distance(c) > P.PRY_R * 0.6] or cands
    first = max(cands, key=lambda c: keepout.distance(c))
    second = max(cands, key=lambda c: min(c.distance(first), 3 * keepout.distance(c)))
    pry = [(c.x, c.y, 2 * P.PRY_R) for c in (first, second)]

    # ----- Z levels -----
    T = P.PLATE_T
    z_face = T + P.RIM_H + P.TAPE_T + 0.15          # cutter face clears the taped rim when bottomed on the trace tops
    z_groove = T + P.TRACE_H + P.TAPE_T + P.TOP_CL
    z_tooth = T - P.MOAT_D + P.TOOTH_FLOOR_CL
    z_badge = -P.GAP                                # badge front face when seated on the shim
    z_lip = -(P.GAP + P.PCB_T + (P.SHIM_T if args.style == 'slide' else 0))
    z_boss = T + P.TRACE_H + 0.3                     # key rides above the traces
    z_post = z_boss + P.KEY_SLOT_H + P.POST_CAP
    z_tray = z_lip - P.LIP_T

    ops = Ops(args.origin)
    ops.add('plateBase', 'board', 'add', 0, T - P.MOAT_D, plate)
    ops.add('plateTopWithMoats', 'board', 'add', T - P.MOAT_D - EPS, T, plate_top)
    ops.add('traces', 'board', 'add', T - EPS, T + P.TRACE_H, cu)
    ops.add('shearRim', 'board', 'add', T - EPS, T + P.RIM_H, rim)
    ops.add('postBosses', 'board', 'add', T - EPS, z_boss, unary_union(bosses))
    ops.add('backRecess', 'board', 'cut', -0.01, P.BACK_RECESS_D, back_tracks.intersection(plate))
    ops.add('pogoHoles', 'board', 'cut', -1, T + P.TRACE_H + 1, circles=pogo_holes)
    ops.add('viaHoles', 'board', 'cut', -1, T + P.TRACE_H + 1, circles=via_holes)
    ops.add('fingerHoles', 'board', 'cut', -1, T + P.TRACE_H + 1, circles=open_holes)
    ops.add('buttonReliefPockets', 'board', 'cut', -0.01, P.ACTUATOR_POCKET_DEPTH, circles=pockets)
    flange_pocket = P.PLUNGER_FLANGE + 0.3
    ops.add('plungerFlangePockets', 'board', 'cut', -0.01, 1.4, circles=[(x, y, d + 2 * flange_pocket) for x, y, d in open_holes])
    sockets = [(x, y, P.SOCKET_D) for x, y in cutter_pins]
    ops.add('sockets', 'board', 'cut', -1, T + 1, circles=sockets)
    ops.add('postHoles', 'board', 'cut', -1, z_boss + 1, circles=[(x, y, P.POST_HOLE_D) for x, y in posts])
    ops.add('postHoleMouth', 'board', 'cut', -0.01, P.SOCKET_CB, circles=[(x, y, P.POST_HOLE_D + 1.0) for x, y in posts])
    ops.add('socketMouthTop', 'board', 'cut', T - P.SOCKET_CB, T + 0.01, circles=[(x, y, P.SOCKET_D + 1.0) for x, y in cutter_pins])

    ops.add('cutterBack', 'cutter', 'add', z_groove, z_face + P.CUTTER_T, plate)
    ops.add('cutterFaceWithGrooves', 'cutter', 'add', z_face, z_groove + EPS, cutter_face)
    ops.add('teeth', 'cutter', 'add', z_tooth, z_face + EPS, teeth)
    ops.pins('cutterPins', 'cutter', 0.3, z_face + EPS, cutter_pins, P.PIN_D, up=False)
    ops.add('fingerHolesCutter', 'cutter', 'cut', z_tooth - 1, z_face + P.CUTTER_T + 1, circles=open_holes)
    ops.add('bossPockets', 'cutter', 'cut', z_face - 0.01, z_boss + 0.4, geom=unary_union(bosses).buffer(0.5, RES))
    ops.add('pryScoops', 'cutter', 'cut', z_face - 0.01, z_face + P.PRY_D, circles=pry)

    ops.add('trayWalls', 'tray', 'add', z_tray, 0, solidify(walls))
    ops.add('trayLips', 'tray', 'add', z_tray, z_lip, solidify(lips.buffer(EPS, RES)))
    ops.add('posts', 'tray', 'add', -1.0, z_post - 0.8, circles=[(x, y, P.POST_D) for x, y in posts])
    ops.add('postTips', 'tray', 'add', z_post - 0.8 - EPS, z_post, circles=[(x, y, P.POST_D - 1.0) for x, y in posts])
    for k, d in enumerate(dowels):
        top = z_lip + P.PCB_T + 1.5
        ops.add(f'dowel{k}', 'tray', 'add', z_lip - 1.0, top - 1.0, d)
        ops.add(f'dowel{k}Tip', 'tray', 'add', top - 1.0 - EPS, top, d.buffer(-0.5))
    slots = unary_union([affinity.rotate(box(x - P.POST_D, y - P.KEY_SLOT_W / 2, x + P.POST_D, y + P.KEY_SLOT_W / 2), a, origin=(x, y))
                         for (x, y), a in zip(posts, key_angles)])
    ops.add('keySlots', 'tray', 'cut', z_boss, z_boss + P.KEY_SLOT_H, slots)
    # edge clip: bottom jaw sits in a notch in the tray bottom so the tray still stands flat
    jaw_lo = clip_rect(clip_pt, clip_n, min(wall_out, 0) - P.CLIP_REACH, spine0 + P.CLIP_T)
    ops.add('clipNotch', 'tray', 'cut', z_tray - 0.01, z_tray + P.CLIP_T + 0.2, clip_rect(clip_pt, clip_n, min(wall_out, 0) - P.CLIP_REACH - 0.3, spine0 + 0.01).buffer(0.3))

    merge_names = ['board', 'cutter', 'tray', 'clip']
    z_jaw_lo = z_tray + P.CLIP_T + 0.2 - P.CLIP_CL          # top of the bottom jaw, against the notch ceiling
    ops.add('clipSpine', 'clip', 'add', z_jaw_lo - P.CLIP_T, T + P.CLIP_CL + P.CLIP_T, clip_rect(clip_pt, clip_n, spine0, spine0 + P.CLIP_T))
    ops.add('clipTopJaw', 'clip', 'add', T + P.CLIP_CL, T + P.CLIP_CL + P.CLIP_T, clip_rect(clip_pt, clip_n, -P.CLIP_REACH, spine0 + EPS))
    ops.add('clipBottomJaw', 'clip', 'add', z_jaw_lo - P.CLIP_T, z_jaw_lo, clip_rect(clip_pt, clip_n, min(wall_out, 0) - P.CLIP_REACH, spine0 + EPS))
    # captive plungers: the open buttons sit ~4.5 mm below the play surface, too deep for a fingertip
    z_button = -(P.GAP - P.BUTTON_H)
    for k, (x, y, d) in enumerate(open_holes):
        stem = d - 2 * P.PLUNGER_CL
        name = f'plunger{k}'
        ops.add(name + 'Flange', name, 'add', z_button + 0.1, 1.0, circles=[(x, y, stem + 2 * P.PLUNGER_FLANGE)])
        ops.add(name + 'Stem', name, 'add', 1.0 - EPS, T + P.TRACE_H + P.PLUNGER_PROUD, circles=[(x, y, stem)])
        merge_names.append(name)
    # gauge for setting the pogo pins: push each pin in until its tip is flush with the gauge standing on the board back
    protrusion = P.GAP - P.PAD_H + P.POGO_TRAVEL
    gx, gy = plate.bounds[2] + 10, plate.bounds[1] + 10
    gauge = box(gx, gy, gx + 20, gy + 12).difference(box(gx + 7, gy - 1, gx + 13, gy + 8))
    ops.add('pinGauge', 'pinGauge', 'add', -protrusion, 0, gauge)

    if args.style == 'slide':
        ops.add('shim', 'shim', 'add', z_lip, z_lip + P.SHIM_T, shims)
    keys = unary_union([affinity.rotate(box(x - P.KEY_LEN / 2, y - P.KEY_W / 2, x + P.KEY_LEN / 2, y + P.KEY_W / 2)
                                        .union(box(x - P.KEY_LEN / 2 - 5, y - 3, x - P.KEY_LEN / 2, y + 3)), a, origin=(x, y))
                        for (x, y), a in zip(posts, key_angles)])
    ops.add('keys', 'keys', 'add', z_boss + 0.1, z_boss + 0.1 + P.KEY_T, keys)

    stem = re.sub(r'\.kicad_pcb$', '', args.pcb.replace('\\', '/').split('/')[-1])
    ref_loops = reference(badge_pcb, args.turns)
    ref_fs = [ring_pts(l, args.origin) for l in ref_loops]
    text = TEMPLATE % {
        'version': args.fs_version, 'source': args.pcb.replace('\\', '/'),
        'feature_title': f'3DPCB {args.style} set - {stem}',
        'feature_id': 'fab' + args.style.capitalize() + re.sub(r'[^A-Za-z0-9]', '', stem.title()),
        'ops': ',\n'.join(ops.items),
        'ref': '[\n    ' + ',\n    '.join(r for r in ref_fs if r) + '\n]',
        'badge_z': z_badge,
        'merge': '[' + ', '.join(f'"{n}"' for n in merge_names) + ']',
    }
    out = args.out or re.sub(r'\.kicad_pcb$', '', args.pcb) + f'_fab_{args.style}.fs'
    open(out, 'w', encoding='utf8').write(text)

    tooth_w = P.MOAT_W - P.SHEAR_CL - P.TAPE_T - P.SIDE_CL
    print(f'{out}: {len(ops.items)} ops, {len(text) // 1024} KB')
    print(f'  groove width over a 3 mm trace: {3 + 2 * (P.TAPE_T + P.SIDE_CL):.2f} mm; tooth {tooth_w:.2f} wide x {z_face - z_tooth:.2f} tall')
    print(f'  Z: cutter face {z_face:.2f}, badge face {z_badge:.2f}, lip top {z_lip:.2f}, tray bottom {z_tray:.2f}')
    print(f'  holes: {len(pogo_holes)} pogo ({P.POGO_HOLE}), {len(via_holes)} via ({P.VIA_HOLE}); lock posts {[(round(x), round(y)) for x, y in posts]} + edge clip at ({clip_pt.x:.0f}, {clip_pt.y:.0f}), {lever:.1f} mm lift at the pins per mm of hold-down play; cutter pins {[(round(x), round(y)) for x, y in cutter_pins]}')
    print(f'  buttons under the board: {sorted(covered)} -> {P.GAP - P.BUTTON_H + P.ACTUATOR_POCKET_DEPTH:.1f} mm of air over each actuator '
          f'({P.GAP - P.BUTTON_H:.1f} gap + {P.ACTUATOR_POCKET_DEPTH:.1f} pocket); open buttons {sorted(open_refs)} get captive plungers')
    print(f'  pogo pins: set tips {protrusion:.1f} mm below the board back (pin gauge body), giving ~{P.POGO_TRAVEL} mm compression')
    tb = walls.union(lips).bounds
    print(f'  tray footprint: {tb[2] - tb[0]:.0f} x {tb[3] - tb[1]:.0f} mm, {-z_tray + z_post:.1f} mm tall; board {plate.bounds[2] - plate.bounds[0]:.0f} x {plate.bounds[3] - plate.bounds[1]:.0f} mm')
    for a, b, x, y, d in shared:
        print(f'  ! {a} and {b} share a moat near ({x}, {y}) (copper gap {d} mm): score the tape along the moat floor with a knife there')

    if args.preview:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(1, 2, figsize=(20, 9))
        def fill(ax, geom, **kw):
            for p in polys(geom):
                ax.fill(*p.exterior.xy, **kw)
                for h in p.interiors:
                    ax.fill(*h.xy, color='w')
        ax = axes[0]
        ax.set_title('board (grey plate, orange traces, blue moat, red shear rim) + cutter teeth (black)')
        fill(ax, plate, color='0.88'); fill(ax, rim, color='tab:red'); fill(ax, moat, color='tab:blue', alpha=.5)
        fill(ax, teeth, color='k', alpha=.6); fill(ax, cu, color='tab:orange')
        fill(ax, back_tracks.intersection(plate), color='tab:green', alpha=.3)
        for x, y, d in pogo_holes + via_holes + open_holes + sockets + [(x, y, P.POST_HOLE_D) for x, y in posts]:
            ax.add_patch(plt.Circle((x, y), d / 2, color='w', ec='k', lw=.6))
        for x, y, d in pry:
            ax.add_patch(plt.Circle((x, y), d / 2, fill=False, ec='m', lw=1.2))
        ax = axes[1]
        ax.set_title('tray (grey walls, green lips), shim (purple), badge outline, plate outline, pins (tray = blue, cutter = red)')
        fill(ax, walls, color='0.6'); fill(ax, lips, color='tab:green', alpha=.7); fill(ax, shims, color='tab:purple', alpha=.6)
        ax.plot(*rot(badge, args.turns).exterior.xy, 'k-', lw=1); ax.plot(*plate.exterior.xy, color='tab:orange', lw=1)
        for x, y in posts:
            ax.add_patch(plt.Circle((x, y), P.POST_D / 2, color='tab:blue'))
        for d in dowels:
            ax.fill(*d.exterior.xy, color='tab:red')
        fill(ax, unary_union(bosses), color='tab:blue', alpha=.4)
        fill(ax, keys, color='k', alpha=.5)
        fill(ax, jaw_lo, color='m', alpha=.7)
        fill(axes[0], unary_union(bosses), color='tab:cyan')
        for x, y in cutter_pins:
            ax.add_patch(plt.Circle((x, y), P.PIN_D / 2, color='tab:red'))
        for x, y in pogo:
            ax.plot(x, y, 'k.', ms=6)
        for a in axes:
            a.invert_yaxis(); a.set_aspect('equal'); a.grid(alpha=.3)
        fig.savefig(args.preview, dpi=80, bbox_inches='tight')


if __name__ == '__main__':
    main()
