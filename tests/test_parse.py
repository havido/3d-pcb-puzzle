import pytest

from kicad2cad.parse import OutlineError, ParseError, parse_text

HEAD = '(kicad_pcb (version 20241229) (generator_version "9.0") (layers (0 "F.Cu" signal) (2 "B.Cu" signal) (25 "Edge.Cuts" user))\n(net 0 "") (net 1 "GND")\n'
BOX = """
(gr_line (start 0 0) (end 10 0) (layer "Edge.Cuts"))
(gr_line (start 10 0) (end 10 10) (layer "Edge.Cuts"))
(gr_line (start 10 10) (end 0 10) (layer "Edge.Cuts"))
(gr_line (start 0 10) (end 0 0) (layer "Edge.Cuts"))
"""


def board(body: str):
    return parse_text(HEAD + body + ")")


def test_outline_from_lines():
    b = board(BOX)
    assert b.outline.area == pytest.approx(100)
    assert b.outline.bounds == (0, 0, 10, 10)


def test_outline_with_arc_corner_and_interior_cutout():
    b = board("""
    (gr_line (start 0 0) (end 8 0) (layer "Edge.Cuts"))
    (gr_arc (start 8 0) (mid 9.414214 0.585786) (end 10 2) (layer "Edge.Cuts"))
    (gr_line (start 10 2) (end 10 10) (layer "Edge.Cuts"))
    (gr_line (start 10 10) (end 0 10) (layer "Edge.Cuts"))
    (gr_line (start 0 10) (end 0 0) (layer "Edge.Cuts"))
    (gr_circle (center 5 5) (end 6 5) (layer "Edge.Cuts"))
    """)
    assert len(b.outline.interiors) == 1
    corner_loss = 4 - 3.14159265 * 4 / 4
    assert b.outline.area == pytest.approx(100 - corner_loss - 3.14159265, rel=1e-3)


def test_outline_gap_is_reported_with_coordinates():
    with pytest.raises(OutlineError, match=r"not closed near .*\(10\.000, 10\.000\)"):
        board(BOX.replace("(start 10 10) (end 0 10)", "(start 10 9.5) (end 0 10)"))


def test_missing_outline_raises():
    with pytest.raises(OutlineError, match="no board outline"):
        board("")


def test_not_a_board():
    with pytest.raises(ParseError, match="not a KiCad board"):
        parse_text("(kicad_sch (version 1))")


def test_rotated_footprint_pads_drills_and_layers():
    b = board(BOX + """
    (footprint "x" (layer "F.Cu") (at 5 5 90)
      (property "Reference" "J1")
      (pad "1" thru_hole oval (at 2 0 90) (size 2 1) (drill oval 0.6 1.2 (offset 0.1 0)) (layers "*.Cu" "*.Mask") (net 1 "GND"))
      (pad "2" smd rect (at 0 1 90) (size 1 1) (layers "F.Cu" "F.Paste"))
      (pad "3" np_thru_hole circle (at -2 0 90) (size 1 1) (drill 1) (layers "*.Cu")))
    """)
    p1, p2, p3 = b.pads
    assert (p1.x, p1.y) == pytest.approx((5, 3))            # +x of the footprint points up on screen
    assert (p2.x, p2.y) == pytest.approx((6, 5))
    assert p1.ref == "J1" and p1.net == "GND" and p1.angle == 90 and p1.fp_angle == 90
    assert p1.layers == ["F.Cu", "B.Cu"] and p2.layers == ["F.Cu"]
    assert (p1.drill.w, p1.drill.h, p1.drill.plated) == (0.6, 1.2, True)
    assert (p1.drill.x, p1.drill.y) == pytest.approx((5, 2.9))   # offset follows the pad's rotation
    assert p3.drill.plated is False
    assert len(b.drills) == 2


def test_zones_keepouts_and_unfilled_warning():
    b = board(BOX + """
    (zone (net 1) (net_name "GND") (layer "F.Cu") (polygon (pts (xy 1 1) (xy 3 1) (xy 3 3) (xy 1 3)))
      (filled_polygon (layer "F.Cu") (pts (xy 1 1) (xy 3 1) (xy 3 3) (xy 1 3))))
    (zone (net 0) (net_name "") (layers "F.Cu" "B.Cu") (keepout (tracks not_allowed)) (polygon (pts (xy 5 5) (xy 6 5) (xy 6 6))))
    (zone (net 1) (net_name "GND") (layer "B.Cu") (polygon (pts (xy 1 1) (xy 2 1) (xy 2 2) (xy 1 2))))
    """)
    assert b.keepouts == 1
    assert [(z.layer, z.net) for z in b.zones] == [("F.Cu", "GND"), ("B.Cu", "GND")]
    assert b.zones[0].polygons[0].area == pytest.approx(4)
    assert any("has no fill" in w for w in b.warnings)


def test_net_by_number_and_by_name():
    b = board(BOX + """
    (segment (start 1 1) (end 2 2) (width 0.5) (layer "F.Cu") (net 1))
    (segment (start 1 1) (end 2 2) (width 0.5) (layer "F.Cu") (net "VCC"))
    """)
    assert [t.net for t in b.tracks] == ["GND", "VCC"]


def test_text_on_copper_and_custom_pad_warn():
    b = board(BOX + """
    (gr_text "HI" (at 1 1 0) (layer "F.Cu"))
    (gr_text "fine" (at 1 1 0) (layer "F.SilkS"))
    (footprint "x" (layer "F.Cu") (at 5 5) (property "Reference" "U1")
      (pad "1" smd custom (at 0 0) (size 1 1) (layers "F.Cu")))
    """)
    assert len(b.warnings) == 2


def test_old_format_warns():
    b = parse_text(HEAD.replace("20241229", "20221018") + BOX + ")")
    assert any("older than KiCad 8" in w for w in b.warnings)
