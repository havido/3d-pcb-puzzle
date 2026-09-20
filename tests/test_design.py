"""The Design tab's server half (docs/whiteboard-plan.md): document model, KiCad writer/reader,
grid router, live rule checks, and the /api/design/* routes."""
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from conftest import FIXTURES, ROOT  # noqa: E402

sys.path.insert(0, str(ROOT / "web"))

from api import design as d  # noqa: E402


# ---- client (same recipe as test_web_api.py) ----------------------------------------------------

@pytest.fixture(scope="module")
def client(tmp_path_factory):
    import os
    os.environ["KICAD2CAD_STORAGE"] = str(tmp_path_factory.mktemp("storage"))
    for mod in [m for m in list(sys.modules) if m.startswith("api.")]:
        del sys.modules[mod]
    from api.main import app
    with TestClient(app) as c:
        yield c


# ---- a small document used by several tests ------------------------------------------------------

def small_doc() -> dict:
    """100 x 80 mm board, comfortably clear of every default rule in check_rules: the two traces
    never cross and stay >4.6 mm apart, and nothing comes within 4 mm of the outline."""
    return {
        "version": 1, "units": "mm", "grid": 1.0,
        "outline": {"points": [[0, 0], [100, 0], [100, 80], [0, 80]]},
        "nets": [{"name": "A", "color": "#d9822b"}, {"name": "B", "color": "#2b8ad9"}],
        "objects": [
            {"id": "t1", "kind": "trace", "net": "A", "width": 3.2,
             "points": [[20, 20], [20, 50], [50, 50]]},
            {"id": "t2", "kind": "trace", "net": "B", "width": 4.5, "points": [[70, 20], [70, 60]]},
            {"id": "h1", "kind": "hole", "d": 1.5, "at": [85, 15], "role": "pogo", "net": "A"},
            {"id": "h2", "kind": "hole", "d": 1.0, "at": [10, 70], "role": "mount", "net": None},
        ],
    }


# ---- 1. document model + validation ---------------------------------------------------------------

def test_valid_document_parses():
    doc = d.Document.model_validate(small_doc())
    d.validate_document(doc)                       # must not raise
    assert len(doc.objects) == 4


def test_duplicate_ids_rejected():
    raw = small_doc()
    raw["objects"][1]["id"] = "t1"                  # clashes with the first trace
    doc = d.Document.model_validate(raw)
    with pytest.raises(d.DesignError, match="t1"):
        d.validate_document(doc)


def test_unknown_net_rejected():
    raw = small_doc()
    raw["objects"][0]["net"] = "GHOST"
    doc = d.Document.model_validate(raw)
    with pytest.raises(d.DesignError, match="GHOST"):
        d.validate_document(doc)


def test_zero_width_rejected():
    raw = small_doc()
    raw["objects"][0]["width"] = 0
    doc = d.Document.model_validate(raw)
    with pytest.raises(d.DesignError, match="t1"):
        d.validate_document(doc)


def test_zero_diameter_hole_rejected():
    raw = small_doc()
    raw["objects"][2]["d"] = 0
    doc = d.Document.model_validate(raw)
    with pytest.raises(d.DesignError, match="h1"):
        d.validate_document(doc)


def test_degenerate_outline_rejected():
    raw = small_doc()
    raw["outline"] = {"points": [[0, 0], [10, 0]]}       # only two points
    doc = d.Document.model_validate(raw)
    with pytest.raises(d.DesignError, match="outline"):
        d.validate_document(doc)


def test_self_intersecting_outline_rejected():
    raw = small_doc()
    raw["outline"] = {"points": [[0, 0], [10, 10], [10, 0], [0, 10]]}     # a bowtie
    doc = d.Document.model_validate(raw)
    with pytest.raises(d.DesignError, match="outline"):
        d.validate_document(doc)


# ---- 2 & 3. the round trip (the most important test) ----------------------------------------------

def test_round_trip_kicad_write_and_read_back():
    """document -> .kicad_pcb -> kicad2cad.parse.load -> geometry matches within 0.01 mm."""
    from kicad2cad.parse import load

    doc = d.Document.model_validate(small_doc())
    text = d.document_to_kicad(doc)
    path = Path(FIXTURES) / "_design_roundtrip_tmp.kicad_pcb"
    path.write_text(text)
    try:
        board = load(path)

        # outline bbox
        ox0, oy0, ox1, oy1 = d.outline_polygon(doc.outline).bounds
        bx0, by0, bx1, by1 = board.outline.bounds
        assert abs(ox0 - bx0) < 0.01 and abs(oy0 - by0) < 0.01
        assert abs(ox1 - bx1) < 0.01 and abs(oy1 - by1) < 0.01

        # track count: each trace with N points becomes N-1 segments
        traces = [o for o in doc.objects if isinstance(o, d.Trace)]
        expected_segments = sum(len(t.points) - 1 for t in traces)
        f_cu_tracks = [t for t in board.tracks if t.layer == "F.Cu"]
        assert len(f_cu_tracks) == expected_segments

        # every segment born from a given trace keeps that trace's net and width
        by_net = {}
        for t in f_cu_tracks:
            by_net.setdefault(t.net, []).append(t.width)
        for trace in traces:
            assert by_net[trace.net] == [trace.width] * (len(trace.points) - 1)

        # hole diameters: board.drills carries one entry per via, in the same order
        holes = [o for o in doc.objects if isinstance(o, d.Hole)]
        drill_diameters = sorted(round(dr.w, 2) for dr in board.drills)
        assert drill_diameters == sorted(round(h.d, 2) for h in holes)
    finally:
        path.unlink(missing_ok=True)


def test_kicad_to_document_on_the_test_fixture():
    doc = d.kicad_to_document(FIXTURES / "testboard.kicad_pcb")
    bx0, by0, bx1, by1 = d.outline_polygon(doc.outline).bounds
    assert (round(bx0, 1), round(by0, 1), round(bx1, 1), round(by1, 1)) == (100.0, 100.0, 150.0, 140.0)
    # T1-T4, the ARC track and the DIAG segment: 6 unconnected F.Cu tracks, none sharing endpoints
    assert sum(1 for o in doc.objects if isinstance(o, d.Trace)) == 6
    # every drill in the fixture (the via, P1's plated pad, H1's three plain holes)
    assert sum(1 for o in doc.objects if isinstance(o, d.Hole)) == 5


def test_document_to_kicad_via_convert_is_watertight(client):
    r = client.post("/api/design/kicad", json={"document": small_doc()})
    assert r.status_code == 200
    board_id = r.json()["board_id"]
    result = client.post("/api/convert", json={"board_id": board_id, "settings": {}}).json()
    assert result["build"]["watertight"] and result["build"]["triangles"] > 0


# ---- 4. router --------------------------------------------------------------------------------

def test_router_goes_around_an_obstacle_and_keeps_clearance():
    raw = small_doc()
    # a partial wall on net B, open above y=35, splitting the board roughly in half
    raw["objects"] = [{"id": "wall", "kind": "trace", "net": "B", "width": 3.0,
                        "points": [[30, 0], [30, 35]]}]
    doc = d.Document.model_validate(raw)
    path = d.route(doc, (5, 5), (55, 5), net="A", clearance=1.0)
    assert path is not None
    assert path[0] == [5, 5] and path[-1] == [55, 5]

    from shapely.geometry import LineString, Point as SPoint
    wall = LineString([(30, 0), (30, 35)]).buffer(1.5)          # the wall's actual copper (half width 1.5)
    for x, y in path:
        assert wall.distance(SPoint(x, y)) >= 1.0 - 1e-6         # never closer than the requested clearance


def test_router_returns_none_when_walled_in():
    raw = small_doc()
    raw["objects"] = [{"id": "wall", "kind": "trace", "net": "B", "width": 3.0,
                        "points": [[30, 0], [30, 80]]}]           # a full-height wall (board is 80 mm tall)
    doc = d.Document.model_validate(raw)
    assert d.route(doc, (5, 5), (55, 5), net="A", clearance=1.0) is None


# ---- 5. check_rules ---------------------------------------------------------------------------

def test_check_rules_flags_thin_trace_close_nets_and_edge_overrun():
    raw = {
        "outline": {"points": [[0, 0], [60, 0], [60, 50], [0, 50]]},
        "nets": [{"name": "A"}, {"name": "B"}],
        "objects": [
            {"id": "thin", "kind": "trace", "net": "A", "width": 1.0,     # under the 3 mm minimum
             "points": [[10, 10], [10, 20]]},
            {"id": "near_a", "kind": "trace", "net": "A", "width": 3.0, "points": [[20, 30], [30, 30]]},
            {"id": "near_b", "kind": "trace", "net": "B", "width": 3.0, "points": [[20, 32], [30, 32]]},
            {"id": "over_edge", "kind": "trace", "net": "A", "width": 3.0, "points": [[0, 25], [5, 25]]},
        ],
    }
    doc = d.Document.model_validate(raw)
    issues = d.check_rules(doc)
    rules_hit = {(i["rule"], i["object_id"]) for i in issues}
    assert ("min_trace_width", "thin") in rules_hit
    assert ("min_net_gap", "near_a") in rules_hit or ("min_net_gap", "near_b") in rules_hit
    assert ("min_edge_margin", "over_edge") in rules_hit


def test_check_rules_flags_small_hole_and_oversize_board():
    raw = {
        "outline": {"points": [[0, 0], [200, 0], [200, 150], [0, 150]]},   # over the 180 mm default
        "nets": [{"name": "A"}],
        "objects": [{"id": "tiny", "kind": "hole", "d": 0.5, "at": [100, 75], "role": "", "net": "A"}],
    }
    doc = d.Document.model_validate(raw)
    issues = d.check_rules(doc)
    rules_hit = {i["rule"] for i in issues}
    assert "min_hole_diameter" in rules_hit
    assert "max_board_size" in rules_hit


def test_check_rules_custom_thresholds():
    doc = d.Document.model_validate(small_doc())
    assert d.check_rules(doc) == []                                       # clean on the defaults
    tightened = d.check_rules(doc, {"min_trace_width": 10.0})
    assert {i["object_id"] for i in tightened if i["rule"] == "min_trace_width"} == {"t1", "t2"}


# ---- 6. routes --------------------------------------------------------------------------------

def test_api_design_kicad_and_import_round_trip(client):
    r = client.post("/api/design/kicad", json={"document": small_doc()})
    assert r.status_code == 200
    body = r.json()
    assert "board_id" in body and body["bytes"] > 0

    r2 = client.post("/api/design/import", json={"board_id": body["board_id"]})
    assert r2.status_code == 200
    imported = r2.json()["document"]
    assert len(imported["objects"]) == 4
    assert {o["id"] for o in imported["objects"]} == {"t1", "t2", "h1", "h2"}


def test_api_design_kicad_rejects_a_bad_document(client):
    raw = small_doc()
    raw["objects"][0]["net"] = "GHOST"
    r = client.post("/api/design/kicad", json={"document": raw})
    assert r.status_code == 400
    assert "GHOST" in r.json()["detail"]


def test_api_design_import_unknown_board(client):
    r = client.post("/api/design/import", json={"board_id": "nope"})
    assert r.status_code == 404


def test_api_design_route(client):
    r = client.post("/api/design/route",
                     json={"document": small_doc(), "start": [1, 1], "end": [59, 1], "net": "A"})
    assert r.status_code == 200
    assert r.json()["points"][0] == [1, 1]


def test_api_design_route_422_when_no_path(client):
    raw = small_doc()
    raw["objects"] = [{"id": "wall", "kind": "trace", "net": "B", "width": 3.0,
                        "points": [[30, 0], [30, 80]]}]           # board is 80 mm tall: this walls it off
    r = client.post("/api/design/route",
                     json={"document": raw, "start": [5, 5], "end": [55, 5], "net": "A", "clearance": 1.0})
    assert r.status_code == 422


def test_api_design_route_unknown_net(client):
    r = client.post("/api/design/route",
                     json={"document": small_doc(), "start": [1, 1], "end": [2, 2], "net": "GHOST"})
    assert r.status_code == 400


def test_api_design_rules(client):
    r = client.post("/api/design/rules", json={"document": small_doc()})
    assert r.status_code == 200
    assert r.json()["issues"] == []                    # small_doc() is drawn well inside every default


def test_the_real_goose_survives_the_whole_design_loop(client):
    """Open the demo board as a document, hand it back as KiCad, convert it: the loop the
    Design tab drives. Its rule issues must be the known too-close nets and nothing worse."""
    samples = client.get("/api/samples").json()
    goose = next(s for s in samples if s["key"] == "goose")

    doc = client.post("/api/design/import", json={"board_id": goose["board_id"]}).json()["document"]
    assert {n["name"] for n in doc["nets"]} >= {"PENALTY", "GOAL_1", "GOAL_2", "GND"}
    assert sum(1 for o in doc["objects"] if o["kind"] == "trace") >= 4

    back = client.post("/api/design/kicad", json={"document": doc}).json()
    result = client.post("/api/convert", json={"board_id": back["board_id"], "settings": {}}).json()
    assert result["build"]["watertight"] and result["build"]["volume_mm3"] > 1000

    issues = client.post("/api/design/rules", json={"document": doc}).json()["issues"]
    # goose v3 was drawn to 3 mm between nets; automatic shearing wants 4.6 mm (CLAUDE.md),
    # so these spots are expected and are the ones Adit's generator scores by hand.
    assert issues and all(i["rule"] == "min_net_gap" for i in issues)
    assert all(i["severity"] == "warning" for i in issues)
