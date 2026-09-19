"""Phase 4: recipe extras (small drills, alignment holes, extra-layer cuts)."""
import math

import pytest
import trimesh
from shapely.geometry import Point

from conftest import FIXTURES, ROOT
from kicad2cad import load
from kicad2cad.build import Recipe, RecipeError, build, load_recipe, prepare, section
from kicad2cad.parse import parse_text
from kicad2cad.shapes import to_board2d

HEAD = '(kicad_pcb (version 20241229) (generator_version "9.0") (layers (0 "F.Cu" signal) (2 "B.Cu" signal) (25 "Edge.Cuts" user))\n'
BOX = ('(gr_rect (start 0 0) (end 30 20) (layer "Edge.Cuts"))\n'
       '(via (at 10 10) (size 0.8) (drill 0.3) (layers "F.Cu" "B.Cu"))\n'
       '(footprint "x" (layer "F.Cu") (at 20 10) (property "Reference" "J1")\n'
       '  (pad "1" thru_hole circle (at 0 0) (size 1.6 1.6) (drill 0.6) (layers "*.Cu"))\n'
       '  (pad "2" thru_hole circle (at 5 0) (size 2 2) (drill 1.2) (layers "*.Cu")))\n')


def small_board(recipe):
    b2d = to_board2d(parse_text(HEAD + BOX + ")"))
    return prepare(b2d, recipe)


def fab(**kw):
    r = Recipe(arc_chord_mm=0.005, **kw)
    r.validate()
    return r


# ---- small drills ---------------------------------------------------------------------------

def test_small_drills_enlarged():
    b, eff = small_board(fab(small_drill="enlarge"))
    assert eff["drills_enlarged"] == 2 and eff["drills_skipped"] == 0
    assert sorted(min(d.w, d.h) for d in b.drills) == [1.0, 1.0, 1.2]
    assert b.holes.contains(Point(10.45, 10))                     # inside the new Ø1.0, outside the old Ø0.3
    assert not b.merged["F.Cu"].contains(Point(10, 10))
    assert any("enlarged" in w for w in b.warnings)


def test_small_drills_skipped_leave_solid_copper():
    b, eff = small_board(fab(small_drill="skip"))
    assert eff["drills_skipped"] == 2 and len(b.drills) == 1
    assert not b.holes.contains(Point(10, 10))
    assert b.merged["F.Cu"].contains(Point(10, 10))              # the via is now a plain copper dot


def test_small_drills_kept():
    b, eff = small_board(fab(small_drill="keep"))
    assert eff == {"drills_enlarged": 0, "drills_skipped": 0, "alignment_holes": []}
    assert b.holes.contains(Point(10, 10)) and not b.holes.contains(Point(10.45, 10))


def test_badge_fab_preset_enlarges_98_drills(badge):
    _, eff = prepare(to_board2d(badge), load_recipe(ROOT / "params" / "3dpcb.yaml"))
    assert eff["drills_enlarged"] == 98                           # 88 vias + 10 pad drills narrower than 1 mm


# ---- alignment holes ------------------------------------------------------------------------

@pytest.fixture(scope="module")
def tb2d():
    return to_board2d(load(FIXTURES / "testboard.kicad_pcb"))


def test_auto_alignment_holes_keep_clear_and_far_apart(tb2d):
    r = fab(alignment_holes={"positions": "auto"})
    b, eff = prepare(tb2d, r)
    a = r.alignment_holes
    need = a["clearance"] + a["diameter"] / 2 - 1e-6
    assert len(b.alignment) == 2
    for x, y, d in b.alignment:
        p = Point(x, y)
        assert d == a["diameter"]
        assert b.merged["F.Cu"].distance(p) >= need
        assert tb2d.holes.distance(p) >= need                     # the board's own drills
        assert b.outline.exterior.distance(p) >= need and all(r_.distance(p) >= need for r_ in b.outline.interiors)
    (x0, y0, _), (x1, y1, _) = b.alignment
    bx0, by0, bx1, by1 = b.outline.bounds
    assert math.dist((x0, y0), (x1, y1)) >= 0.5 * math.dist((bx0, by0), (bx1, by1))
    bld = build(b, r)
    base = section(bld, r.base_thickness / 2)
    assert all(not base.contains(Point(x, -y)) for x, y, _ in b.alignment)   # real holes in the 3D board


def test_explicit_alignment_positions(tb2d):
    b, _ = prepare(tb2d, fab(alignment_holes={"positions": [[145, 105], [120, 103]]}))
    assert [(x, y) for x, y, _ in b.alignment] == [(145, 105)]    # (120, 103) is on track T1: skipped
    assert any("(120, 103)" in w and "skipped" in w for w in b.warnings)


def test_no_room_for_alignment_holes_warns():
    full = HEAD + '(gr_rect (start 0 0) (end 30 20) (layer "Edge.Cuts"))\n' \
        '(zone (net 0) (net_name "") (layer "F.Cu") (polygon (pts (xy 0 0) (xy 30 0) (xy 30 20) (xy 0 20)))' \
        ' (filled_polygon (layer "F.Cu") (pts (xy 0 0) (xy 30 0) (xy 30 20) (xy 0 20))))\n)'
    b, eff = prepare(to_board2d(parse_text(full)), fab(alignment_holes={"positions": "auto"}))
    assert eff["alignment_holes"] == [] and any("no room" in w for w in b.warnings)


# ---- extra-layer cuts -----------------------------------------------------------------------

@pytest.mark.parametrize("spec, depth", [({"op": "recess", "depth": 1.5}, 1.5), ({"op": "through"}, 2.0)])
def test_extra_layer_cut_removes_area_times_depth(tb2d, expected, spec, depth, tmp_path):
    r = fab(extra_layers={"User.1": spec})
    b, _ = prepare(tb2d, r)
    bld = build(b, r)
    (op,) = bld.extra_layers
    assert op["removed_mm3"] == pytest.approx(expected["user1_area_mm2"] * depth, rel=2e-3)
    cx, cy = 115, -136.5                                          # centre of the User.1 channel, Y flipped
    assert not section(bld, r.base_thickness - 0.1).contains(Point(cx, cy))
    assert section(bld, 0.1).contains(Point(cx, cy)) == (spec["op"] != "through")
    f = tmp_path / "b.stl"
    f.write_bytes(bld.mesh.export(file_type="stl"))
    assert trimesh.load(str(f), file_type="stl").is_watertight


def test_extra_layer_missing_warns(tb2d):
    r = fab(extra_layers={"User.5": {"op": "through"}})
    bld = build(prepare(tb2d, r)[0], r)
    assert bld.extra_layers == [] and any("no shapes on User.5" in w for w in bld.warnings)


# ---- validation ------------------------------------------------------------------------------

@pytest.mark.parametrize("kw, message", [
    ({"extra_layers": {"User.1": {"op": "carve"}}}, "op must be one of"),
    ({"extra_layers": {"User.1": {"op": "recess"}}}, "needs 0 < depth"),
    ({"extra_layers": {"User.1": {"op": "recess", "depth": 2.0}}}, "needs 0 < depth"),
    ({"alignment_holes": {"size": 3}}, "unknown key"),
    ({"alignment_holes": {"diameter": 0}}, "diameter must be > 0"),
    ({"alignment_holes": {"positions": [1, 2]}}, "positions must be"),
    ({"small_drill": "drill"}, "small_drill must be"),
    ({"min_drill": 0}, "min_drill must be > 0"),
])
def test_recipe_validation(kw, message):
    with pytest.raises(RecipeError, match=message):
        Recipe(**kw).validate()


def test_shipped_fab_preset():
    r = load_recipe(ROOT / "params" / "3dpcb.yaml")
    assert r.small_drill == "enlarge" and r.min_drill == 1.0
    assert r.alignment_holes == {"diameter": 3.0, "positions": "auto", "clearance": 3.0}
    assert r.extra_layers == {}
