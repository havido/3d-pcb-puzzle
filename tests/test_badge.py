"""Golden numbers from the real badge board (docs/kicad2cad-plan.md §5)."""
import math
from collections import Counter, defaultdict

import pytest

from kicad2cad.summary import summarize

HOLES = [(74.58, 33.79), (132.28, 33.82), (74.59, 173.21), (132.29, 173.24)]


def test_outline(badge):
    x0, y0, x1, y1 = badge.outline.bounds
    assert (x0, y0, x1, y1) == pytest.approx((55.86, 29.92, 150.89, 177.26), abs=0.01)
    centres = sorted((round((r.bounds[0] + r.bounds[2]) / 2, 2), round((r.bounds[1] + r.bounds[3]) / 2, 2))
                     for r in badge.outline.interiors)
    assert centres == pytest.approx(sorted(HOLES), abs=0.01)
    for r in badge.outline.interiors:
        assert r.bounds[2] - r.bounds[0] == pytest.approx(4.45, abs=0.01)


def test_copper_counts(badge):
    s = summarize(badge)
    f = s["copper"]["F.Cu"]
    assert (f["segments"], f["arcs"], f["pads"], f["vias"]) == (634, 0, 315, 88)
    assert s["vias_by_size_drill"] == {"0.8/0.4": 60, "0.6/0.3": 24, "1.2/0.6": 4}
    assert f["zones"] == [{"net": "GND", "filled_polygons": 15}]
    assert f["graphics"] == {"circle": 2, "rect": 1}
    assert s["keepouts_ignored"] == 2
    assert s["drills"]["oval"] == 4


def test_pad_shapes(badge):
    shapes = Counter(p.shape for p in badge.pads)
    assert shapes == {"rect": 202, "roundrect": 197, "oval": 52, "circle": 12, "custom": 1}


def test_expected_warnings(badge):
    assert len(badge.warnings) == 2
    assert sum("gr_text" in w for w in badge.warnings) == 1
    assert sum("custom shape" in w for w in badge.warnings) == 1


@pytest.mark.parametrize("ref, number, xy, net", [
    ("SW2", "1", (73.83, 118.93), "GND"),
    ("SW10", "1", (116.54, 152.10), "ESP32_BOOT"),   # footprint rotated 180°
    ("U8", "1", (107.60, 138.09), "SR_SHLD"),        # footprint rotated 90°
])
def test_pad_positions(badge, ref, number, xy, net):
    pad = next(p for p in badge.pads if p.ref == ref and p.number == number)
    assert (pad.x, pad.y) == pytest.approx(xy, abs=0.01)
    assert pad.net == net


def test_pads_land_on_their_tracks(badge):
    """Rotation check: pads must sit exactly on the end points of same-net tracks.

    With the correct formula 331 pads (148 on 90°/270° footprints) land within 0.05 mm,
    and the same at 0.01 mm, so nothing is borderline. The opposite rotation sign gives 185 (2).
    """
    ends = defaultdict(list)
    for t in badge.tracks:
        ends[(t.layer, t.net)] += [t.start, t.end]
    hits = rotated = 0
    for p in badge.pads:
        pts = [q for layer in p.layers for q in ends[(layer, p.net)]]
        if p.net and pts and min(math.dist((p.x, p.y), q) for q in pts) < 0.05:
            hits += 1
            rotated += p.fp_angle % 180 != 0
    assert hits >= 331 and rotated >= 148, (hits, rotated)
