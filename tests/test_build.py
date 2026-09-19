"""Phase 3: Board2D + recipe → 3D solid (docs/kicad2cad-plan.md §6)."""
import pytest
from shapely.geometry import Point

from conftest import FIXTURES
from kicad2cad import load
from kicad2cad.build import Recipe, RecipeError, build, load_recipe, section
from kicad2cad.shapes import to_board2d

FINE = 0.001


@pytest.fixture(scope="module")
def testboard3d():
    r = Recipe(arc_chord_mm=FINE)
    b2d = to_board2d(load(FIXTURES / "testboard.kicad_pcb", arc_chord_mm=FINE), chord=FINE)
    return r, b2d, build(b2d, r)


def test_mesh_is_printable(testboard3d):
    _, _, bld = testboard3d
    assert bld.mesh.is_watertight and bld.mesh.is_volume and bld.mesh.volume > 0


def test_volume_matches_hand_computed(testboard3d, expected):
    r, _, bld = testboard3d
    base_area = expected["outline"]["area_mm2"] - expected["holes_area_mm2"]
    want = base_area * r.base_thickness + expected["copper_area_total_mm2"] * r.copper_raise
    assert bld.mesh.volume == pytest.approx(want, rel=1e-3)


def test_volume_matches_its_own_areas_exactly(testboard3d):
    r, _, bld = testboard3d
    assert bld.mesh.volume == pytest.approx(bld.base_area * r.base_thickness + bld.copper_area * r.copper_raise, rel=1e-6)


def test_bounds_are_the_outline_with_y_flipped(testboard3d, expected):
    r, _, bld = testboard3d
    x0, y0, x1, y1 = expected["outline"]["bbox"]
    assert bld.mesh.bounds.ravel().tolist() == pytest.approx([x0, -y1, 0, x1, -y0, r.base_thickness + r.copper_raise], abs=1e-6)


def test_not_mirrored_copper_is_where_kicad_shows_it(testboard3d):
    """The L marker's foot is at KiCad (106, 111). After the one Y flip it must be at (106, −111), and
    nothing may appear at the mirrored places."""
    r, _, bld = testboard3d
    top = section(bld, r.base_thickness + r.copper_raise / 2)
    assert top.contains(Point(106, -111))
    assert not top.contains(Point(106, -103))            # above the foot, inside the L's corner: empty
    assert not top.contains(Point(106, 111))             # Y not flipped
    assert not top.contains(Point(-106, -111))           # X mirrored


def test_base_layer_has_the_holes(testboard3d):
    r, _, bld = testboard3d
    base = section(bld, r.base_thickness / 2)
    assert not base.contains(Point(144, -129))           # the Ø6 cut-out
    assert not base.contains(Point(141, -110))           # the via drill
    assert base.contains(Point(120, -125))               # plain board


def test_badge_builds_watertight_and_fast(badge):
    import time
    t0 = time.perf_counter()
    bld = build(to_board2d(badge), Recipe())
    assert time.perf_counter() - t0 < 60
    assert bld.mesh.is_watertight and bld.mesh.is_volume
    assert any("B.Cu is ignored" in w for w in bld.warnings)


def test_recipe_loading(tmp_path):
    f = tmp_path / "r.yaml"
    f.write_text("base_thickness: 3.0\ncopper_raise: 0.4\n")
    r = load_recipe(f)
    assert (r.base_thickness, r.copper_raise, r.copper_layer) == (3.0, 0.4, "F.Cu")
    f.write_text("base_thicknes: 3.0\n")
    with pytest.raises(RecipeError, match="unknown recipe key"):
        load_recipe(f)
    f.write_text("copper_raise: 0\n")
    with pytest.raises(RecipeError, match="must be > 0"):
        load_recipe(f)


def test_shipped_recipe_loads():
    from conftest import ROOT
    r = load_recipe(ROOT / "params" / "3dpcb.yaml")
    assert r.pending_warnings() == []


def test_phase4_options_warn_until_implemented():
    assert Recipe(extra_layers={"User.1": {"op": "recess", "depth": 1.5}}).pending_warnings()


def test_recipe_changes_the_output(testboard3d):
    _, b2d, bld = testboard3d
    thicker = build(b2d, Recipe(base_thickness=3.0, arc_chord_mm=FINE))
    assert thicker.mesh.volume == pytest.approx(bld.mesh.volume + bld.base_area * 1.0, rel=1e-6)
