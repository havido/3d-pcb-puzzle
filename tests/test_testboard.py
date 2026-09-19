"""The synthetic test board (docs/kicad2cad-plan.md §4) against its hand-computed expectations."""
import importlib.util

import pytest

from conftest import FIXTURES
from kicad2cad.summary import summarize


def test_fixture_file_is_up_to_date():
    spec = importlib.util.spec_from_file_location("make_testboard", FIXTURES / "make_testboard.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert (FIXTURES / "testboard.kicad_pcb").read_text() == mod.board_text(), \
        "run: python tests/fixtures/make_testboard.py"


def test_outline(testboard, expected):
    e = expected["outline"]
    assert testboard.outline.bounds == pytest.approx(e["bbox"])
    assert len(testboard.outline.interiors) == e["holes"]
    assert testboard.outline.area == pytest.approx(e["area_mm2"], rel=1e-3)   # arcs/circles are sampled


def test_counts(testboard, expected):
    c, s = expected["counts"], summarize(testboard)
    fcu = s["copper"]["F.Cu"]
    assert (fcu["segments"], fcu["arcs"], fcu["vias"], fcu["pads"]) == (c["segments"], c["arcs"], c["vias"], c["pads_on_F.Cu"])
    assert len(testboard.pads) == c["pads"]
    assert s["pad_shapes"] == c["pad_shapes"]
    assert (s["drills"]["total"], s["drills"]["plated"]) == (c["drills"], c["plated_drills"])
    assert len(fcu["zones"]) == c["zones_F.Cu"]
    assert len(testboard.graphics) == c["copper_graphics"]
    assert s["user_layers"] == c["user_layers"]
    assert len(testboard.warnings) == c["warnings"]


def test_rotated_footprint_pad_positions(testboard, expected):
    p1 = {p.number: (p.x, p.y) for p in testboard.pads if p.ref == "P1"}
    for number, xy in expected["pads_board_xy"].items():
        assert p1[number] == pytest.approx(xy, abs=1e-6)


def test_hole_sizes(testboard, expected):
    npth = sorted(d.w for d in testboard.drills if not d.plated)
    assert npth == expected["hole_diameters"]
