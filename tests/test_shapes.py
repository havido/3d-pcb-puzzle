import math

import pytest
from shapely.geometry import Point

from kicad2cad.geom import place
from kicad2cad.model import Drill, Graphic, Pad
from kicad2cad.shapes import capsule, drill_shape, graphic_shape, pad_shape, roundrect, stadium

FINE = 0.00005  # chord error for formula checks (area error ≈ 4/3 · FINE / r)


def pad(shape, w, h, angle=0.0, kind="smd", drill=None, rratio=0.0):
    return Pad("U1", "1", kind, shape, 10.0, 20.0, angle, angle, w, h, rratio, ["F.Cu"], None, drill)


def test_track_area_matches_formula():
    w, length = 2.0, 25.0
    assert capsule((0, 0), (length, 0), w, FINE).area == pytest.approx(w * length + math.pi * (w / 2) ** 2, rel=1e-4)


def test_zero_length_track_is_a_dot():
    assert capsule((1, 1), (1, 1), 2.0, FINE).area == pytest.approx(math.pi, rel=1e-4)


@pytest.mark.parametrize("w, h", [(4, 2), (2, 4), (3, 3)])
def test_oval_is_a_stadium(w, h):
    s, r = min(w, h), min(w, h) / 2
    assert stadium(0, 0, w, h, FINE).area == pytest.approx((max(w, h) - s) * s + math.pi * r * r, rel=1e-4)


def test_roundrect_area():
    r = 0.25 * 2
    assert roundrect(0, 0, 3, 2, r, FINE).area == pytest.approx(3 * 2 - (4 - math.pi) * r * r, rel=1e-4)


def test_rotated_rect_pad_swaps_its_bounding_box():
    x0, y0, x1, y1 = pad_shape(pad("rect", 4, 2, angle=90), FINE).bounds
    assert (x1 - x0, y1 - y0) == pytest.approx((2, 4))


def test_shape_rotation_matches_pad_placement():
    """A corner of a 30°-rotated rect must be where `place` puts it: same direction everywhere."""
    corners = list(pad_shape(pad("rect", 4, 2, angle=30), FINE).exterior.coords)
    want = place(10, 20, 30, 2, 1)                     # the pad-local corner (+2, +1)
    assert min(math.dist(c, want) for c in corners) < 1e-9


def test_bare_npth_has_no_copper_but_npth_with_ring_does():
    d = Drill(10, 20, 1, 1, 0, False, None)
    assert pad_shape(pad("circle", 1, 1, kind="np_thru_hole", drill=d), FINE).is_empty
    assert pad_shape(pad("circle", 2, 2, kind="np_thru_hole", drill=d), FINE).area > 0


def test_oval_drill_rotates_with_its_pad():
    x0, y0, x1, y1 = drill_shape(Drill(0, 0, 0.6, 1.2, 90, True, None), FINE).bounds
    assert (x1 - x0, y1 - y0) == pytest.approx((1.2, 0.6))


def test_graphics_filled_stroked_and_empty():
    square = [(0, 0), (2, 0), (2, 2), (0, 2), (0, 0)]
    assert graphic_shape(Graphic("poly", "F.Cu", square, 0, True, True), FINE).area == pytest.approx(4)
    ring = graphic_shape(Graphic("poly", "F.Cu", square, 0.2, False, True), FINE)
    assert ring.area == pytest.approx(8 * 0.2, rel=1e-2) and not ring.contains(Point(1, 1))
    assert graphic_shape(Graphic("poly", "F.Cu", square, 0, False, True), FINE).is_empty
