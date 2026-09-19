"""Write the kicad2cad test board and its expected values (docs/kicad2cad-plan.md §4).

    python tests/fixtures/make_testboard.py    # -> testboard.kicad_pcb + testboard.expected.json

Every expected number is worked out here with plain geometry formulas, never by
running kicad2cad, so the tests can't agree with the code by accident. No two copper
features overlap, so expected areas are simple sums.

The board is 50 x 40 mm at KiCad (100, 100)..(150, 140). "Top" means small Y, as in
KiCad's own view.
"""
import json
import math
from pathlib import Path

HERE = Path(__file__).parent
X0, Y0, X1, Y1 = 100.0, 100.0, 150.0, 140.0
CORNER_R = 5.0                                   # top-right corner is rounded
CUTOUT = (144.0, 129.0, 3.0)                     # interior circle cut-out: x, y, r
TRACKS = [(1.0, 103.0), (1.5, 107.0), (2.0, 111.5), (3.0, 117.0)]   # (width, y), from x 112 to 137
TRACK_X = (112.0, 137.0)
ARC = dict(center=(113.0, 132.0), r=8.0, width=2.0)   # 90° arc from angle 180° to 270°
DIAG = dict(start=(118.0, 123.0), end=(124.0, 129.0), width=2.0)
L_MARKER = [(102, 102), (104, 102), (104, 110), (108, 110), (108, 112), (102, 112)]
P1 = dict(at=(130.0, 127.0), rot=90.0)           # rotated footprint with 4 pad shapes
VIA = dict(at=(141.0, 110.0), size=2.0, drill=1.0)
ZONE = [(140, 113), (148, 113), (148, 121), (140, 121)]
H1 = dict(at=(137.0, 132.5), holes=[(-2.5, 1.0), (0.0, 1.5), (3.0, 2.0)])   # (local x, diameter)
CHANNEL = ((105.0, 134.5), (125.0, 138.5))       # User.1 rectangle (goose-style channel)

LAYERS = """  (layers
    (0 "F.Cu" signal)
    (2 "B.Cu" signal)
    (13 "F.Paste" user)
    (15 "B.Paste" user)
    (5 "F.SilkS" user "F.Silkscreen")
    (7 "B.SilkS" user "B.Silkscreen")
    (1 "F.Mask" user)
    (3 "B.Mask" user)
    (25 "Edge.Cuts" user)
    (31 "F.CrtYd" user "F.Courtyard")
    (35 "F.Fab" user)
    (39 "User.1" user)
    (41 "User.2" user)
  )"""
NETS = ["", "GND", "T1", "T2", "T3", "T4", "ARC", "DIAG", "P1A", "P1B", "P1C", "P1D"]


def f(v: float) -> str:
    return f"{v:.4f}".rstrip("0").rstrip(".")


def stroke(w: float) -> str:
    return f"(stroke (width {f(w)}) (type solid))"


def net(name: str) -> str:
    return f"(net {NETS.index(name)})"


def board_text() -> str:
    cx, cy = X1 - CORNER_R, Y0 + CORNER_R
    mid = (cx + CORNER_R * math.cos(math.radians(-45)), cy + CORNER_R * math.sin(math.radians(-45)))
    edges = [
        f'(gr_line (start {f(X0)} {f(Y0)}) (end {f(cx)} {f(Y0)}) {stroke(0.05)} (layer "Edge.Cuts"))',
        f'(gr_arc (start {f(cx)} {f(Y0)}) (mid {f(mid[0])} {f(mid[1])}) (end {f(X1)} {f(cy)}) {stroke(0.05)} (layer "Edge.Cuts"))',
        f'(gr_line (start {f(X1)} {f(cy)}) (end {f(X1)} {f(Y1)}) {stroke(0.05)} (layer "Edge.Cuts"))',
        f'(gr_line (start {f(X1)} {f(Y1)}) (end {f(X0)} {f(Y1)}) {stroke(0.05)} (layer "Edge.Cuts"))',
        f'(gr_line (start {f(X0)} {f(Y1)}) (end {f(X0)} {f(Y0)}) {stroke(0.05)} (layer "Edge.Cuts"))',
        f'(gr_circle (center {f(CUTOUT[0])} {f(CUTOUT[1])}) (end {f(CUTOUT[0] + CUTOUT[2])} {f(CUTOUT[1])}) {stroke(0.05)} (fill no) (layer "Edge.Cuts"))',
    ]
    pts = " ".join(f"(xy {x} {y})" for x, y in L_MARKER)
    graphics = [
        f'(gr_poly (pts {pts}) {stroke(0)} (fill yes) (layer "F.Cu"))',
        f'(gr_rect (start {f(CHANNEL[0][0])} {f(CHANNEL[0][1])}) (end {f(CHANNEL[1][0])} {f(CHANNEL[1][1])}) {stroke(0.1)} (fill yes) (layer "User.1"))',
        '(gr_text "HONK" (at 140 137 0) (layer "F.Cu") (effects (font (size 1.5 1.5) (thickness 0.3))))',
    ]
    tracks = [f'(segment (start {f(TRACK_X[0])} {f(y)}) (end {f(TRACK_X[1])} {f(y)}) (width {f(w)}) (layer "F.Cu") {net(f"T{i + 1}")})'
              for i, (w, y) in enumerate(TRACKS)]
    (ax, ay), r = ARC["center"], ARC["r"]
    tracks.append(f'(arc (start {f(ax - r)} {f(ay)}) (mid {f(ax - r * math.cos(math.pi / 4))} {f(ay - r * math.sin(math.pi / 4))}) '
                  f'(end {f(ax)} {f(ay - r)}) (width {f(ARC["width"])}) (layer "F.Cu") {net("ARC")})')
    tracks.append(f'(segment (start {f(DIAG["start"][0])} {f(DIAG["start"][1])}) (end {f(DIAG["end"][0])} {f(DIAG["end"][1])}) '
                  f'(width {f(DIAG["width"])}) (layer "F.Cu") {net("DIAG")})')
    via = f'(via (at {f(VIA["at"][0])} {f(VIA["at"][1])}) (size {f(VIA["size"])}) (drill {f(VIA["drill"])}) (layers "F.Cu" "B.Cu") {net("GND")})'
    rot = f(P1["rot"])
    p1 = f'''(footprint "test:P1" (layer "F.Cu") (at {f(P1["at"][0])} {f(P1["at"][1])} {rot})
    (property "Reference" "P1" (at 0 -8 {rot}) (layer "F.SilkS"))
    (pad "1" thru_hole circle (at -4.5 0 {rot}) (size 3 3) (drill 1) (layers "*.Cu" "*.Mask") {net("P1A")})
    (pad "2" smd rect (at 0 0 {rot}) (size 4 2) (layers "F.Cu" "F.Mask" "F.Paste") {net("P1B")})
    (pad "3" smd oval (at 5 0 {rot}) (size 4 2) (layers "F.Cu" "F.Mask" "F.Paste") {net("P1C")})
    (pad "4" smd roundrect (at 0 4 {rot}) (size 3 2) (layers "F.Cu" "F.Mask" "F.Paste") (roundrect_rratio 0.25) {net("P1D")})
  )'''
    holes = "\n".join(f'    (pad "" np_thru_hole circle (at {f(x)} 0) (size {f(d)} {f(d)}) (drill {f(d)}) (layers "*.Cu" "*.Mask"))'
                      for x, d in H1["holes"])
    h1 = f'''(footprint "test:H1" (layer "F.Cu") (at {f(H1["at"][0])} {f(H1["at"][1])})
    (property "Reference" "H1" (at 0 -3 0) (layer "F.SilkS"))
{holes}
  )'''
    zpts = " ".join(f"(xy {x} {y})" for x, y in ZONE)
    zone = f'''(zone {net("GND")} (net_name "GND") (layer "F.Cu") (hatch edge 0.5)
    (connect_pads (clearance 0.5)) (min_thickness 0.25) (fill yes (thermal_gap 0.5) (thermal_bridge_width 0.5))
    (polygon (pts {zpts}))
    (filled_polygon (layer "F.Cu") (pts {zpts}))
  )'''
    nets = "\n".join(f'  (net {i} "{n}")' for i, n in enumerate(NETS))
    body = "\n".join("  " + s for s in edges + graphics + tracks + [via, p1, h1, zone])
    return f'''(kicad_pcb (version 20241229) (generator "make_testboard") (generator_version "9.0")
  (general (thickness 1.6) (legacy_teardrops no))
  (paper "A4")
{LAYERS}
{nets}
{body}
)
'''


def expected() -> dict:
    pi = math.pi
    capsule = lambda w, length: w * length + pi * (w / 2) ** 2
    corner_loss = CORNER_R ** 2 - pi * CORNER_R ** 2 / 4
    outline_area = (X1 - X0) * (Y1 - Y0) - corner_loss - pi * CUTOUT[2] ** 2
    diag_len = math.dist(DIAG["start"], DIAG["end"])
    ro, ri = ARC["r"] + ARC["width"] / 2, ARC["r"] - ARC["width"] / 2
    l_area = 2 * 10 + 4 * 2
    copper = {
        "l_marker": l_area,
        "tracks": sum(capsule(w, TRACK_X[1] - TRACK_X[0]) for w, _ in TRACKS),
        "arc": (pi / 2) / 2 * (ro ** 2 - ri ** 2) + pi * (ARC["width"] / 2) ** 2,
        "diag": capsule(DIAG["width"], diag_len),
        "pad_circle_minus_drill": pi * (1.5 ** 2 - 0.5 ** 2),
        "pad_rect": 4 * 2,
        "pad_oval": (4 - 2) * 2 + pi * 1 ** 2,
        "pad_roundrect": 3 * 2 - (4 - pi) * (0.25 * 2) ** 2,
        "via_minus_drill": pi * ((VIA["size"] / 2) ** 2 - (VIA["drill"] / 2) ** 2),
        "zone": 8 * 8,
    }
    return {
        "outline": {"bbox": [X0, Y0, X1, Y1], "area_mm2": outline_area, "holes": 1,
                    "cutout_center": list(CUTOUT[:2]), "cutout_diameter": 2 * CUTOUT[2]},
        "counts": {"segments": len(TRACKS) + 1, "arcs": 1, "vias": 1, "pads": 7, "pads_on_F.Cu": 7,
                   "pad_shapes": {"thru_hole/circle": 1, "smd/rect": 1, "smd/oval": 1, "smd/roundrect": 1,
                                  "np_thru_hole/circle": 3},
                   "drills": 5, "plated_drills": 2, "zones_F.Cu": 1, "copper_graphics": 1,
                   "user_layers": {"User.1": 1}, "warnings": 1},
        "pads_board_xy": {"1": [130.0, 131.5], "2": [130.0, 127.0], "3": [130.0, 122.0], "4": [134.0, 127.0]},
        "hole_diameters": [d for _, d in H1["holes"]],
        "copper_area_mm2": copper,
        "copper_area_total_mm2": sum(copper.values()),
        "user1_area_mm2": (CHANNEL[1][0] - CHANNEL[0][0]) * (CHANNEL[1][1] - CHANNEL[0][1]),
    }


if __name__ == "__main__":
    (HERE / "testboard.kicad_pcb").write_text(board_text())
    (HERE / "testboard.expected.json").write_text(json.dumps(expected(), indent=1) + "\n")
    print("wrote", HERE / "testboard.kicad_pcb", "and testboard.expected.json")
