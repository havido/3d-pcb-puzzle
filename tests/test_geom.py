import math

import pytest

from kicad2cad.geom import arc_points, circle_points, circle_through, place


@pytest.mark.parametrize("rot, local, expected", [
    (0, (1, 2), (11, 22)),
    (90, (1, 0), (10, 19)),       # KiCad: +90° turns the footprint's +x to screen-up (smaller y)
    (90, (0, 1), (11, 20)),
    (180, (1, 2), (9, 18)),
    (-90, (1, 0), (10, 21)),
])
def test_place_matches_kicad_rotation(rot, local, expected):
    x, y = place(10, 20, rot, *local)
    assert (round(x, 9), round(y, 9)) == expected


def test_circle_through_three_points():
    assert circle_through((0, 1), (1, 0), (0, -1)) == pytest.approx((0, 0, 1))
    assert circle_through((0, 0), (1, 1), (2, 2)) is None


@pytest.mark.parametrize("mid", [(-1 / math.sqrt(2), -1 / math.sqrt(2)), (1 / math.sqrt(2), 1 / math.sqrt(2))])
def test_arc_points_follow_mid_and_stay_within_chord_error(mid):
    start, end = (-1.0, 0.0), (0.0, -1.0)
    pts = arc_points(start, mid, end, max_err=0.001)
    assert pts[0] == start and pts[-1] == end
    for a, b in zip(pts, pts[1:]):                      # every chord's midpoint is within max_err of the circle
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        assert 1 - math.hypot(mx, my) <= 0.001 + 1e-12
    # the short way round (via the first mid) is ~90°, the long way ~270°
    length = sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))
    assert length == pytest.approx(math.pi / 2 if mid[0] < 0 else 3 * math.pi / 2, rel=1e-3)


def test_circle_points_closed_and_accurate():
    pts = circle_points(5, 5, 3, max_err=0.01)
    assert pts[0] == pts[-1]
    assert all(abs(math.hypot(x - 5, y - 5) - 3) < 1e-9 for x, y in pts)
