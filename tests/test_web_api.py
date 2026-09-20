"""The web API around kicad2cad (web/api)."""
import json
import sys
import zipfile
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from conftest import ROOT  # noqa: E402

sys.path.insert(0, str(ROOT / "web"))


@pytest.fixture(scope="module")
def client(tmp_path_factory, monkeypatch_session=None):
    import os
    os.environ["KICAD2CAD_STORAGE"] = str(tmp_path_factory.mktemp("storage"))
    for mod in [m for m in list(sys.modules) if m.startswith("api.")]:
        del sys.modules[mod]
    from api.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def testboard_id(client):
    samples = client.get("/api/samples").json()
    return next(s["board_id"] for s in samples if s["key"] == "testboard")


def test_health_and_samples(client):
    assert client.get("/api/health").json()["ok"] is True
    keys = {s["key"] for s in client.get("/api/samples").json()}
    assert {"testboard", "goose", "badge"} <= keys


def test_recipe_schema_matches_the_converter(client):
    schema = client.get("/api/recipe/schema").json()
    from api.convert import recipe_from
    assert recipe_from(schema["defaults"])                      # the defaults are a valid recipe
    assert {f["name"] for f in schema["fields"]} == set(schema["defaults"])


def test_convert_and_cache(client, testboard_id):
    body = {"board_id": testboard_id, "settings": {"alignment_holes_on": True}}
    first = client.post("/api/convert", json=body).json()
    assert first["cached"] is False
    assert [s["name"] for s in first["stages"]] == ["parse", "shapes", "prepare", "build", "export"]
    assert first["build"]["watertight"] and first["build"]["triangles"] > 0
    assert len(first["build"]["recipe_effects"]["alignment_holes"]) == 2
    again = client.post("/api/convert", json=body).json()
    assert again["cached"] is True and again["job_id"] == first["job_id"]


def test_settings_change_the_job_and_the_board(client, testboard_id):
    a = client.post("/api/convert", json={"board_id": testboard_id, "settings": {}}).json()
    b = client.post("/api/convert", json={"board_id": testboard_id, "settings": {"base_thickness": 3.0}}).json()
    assert a["job_id"] != b["job_id"]
    assert b["build"]["volume_mm3"] > a["build"]["volume_mm3"]


def test_files_and_bundle(client, testboard_id):
    job = client.post("/api/convert", json={"board_id": testboard_id, "settings": {}}).json()["job_id"]
    stl = client.get(f"/api/jobs/{job}/files/board.stl")
    assert stl.status_code == 200 and stl.content[:5] != b"solid" and len(stl.content) > 1000
    assert client.get(f"/api/jobs/{job}/files/layers/F.Cu.svg").status_code == 200
    z = client.get(f"/api/jobs/{job}/bundle.zip")
    assert z.status_code == 200 and len(z.content) < 5_000_000            # a zip must never contain itself
    names = zipfile.ZipFile(__import__("io").BytesIO(z.content)).namelist()
    assert "board.stl" in names and "bundle.zip" not in names


def test_upload(client):
    data = (ROOT / "tests" / "fixtures" / "testboard.kicad_pcb").read_bytes()
    r = client.post("/api/boards", files={"file": ("testboard.kicad_pcb", data, "application/octet-stream")})
    assert r.status_code == 200 and r.json()["bytes"] == len(data)
    assert client.post("/api/boards", files={"file": ("x.txt", b"nope", "text/plain")}).status_code == 400
    assert client.post("/api/boards", files={"file": ("x.kicad_pcb", b"not a board", "text/plain")}).status_code == 400


def test_errors(client, testboard_id):
    assert client.post("/api/convert", json={"board_id": "nope", "settings": {}}).status_code == 404
    bad = client.post("/api/convert", json={"board_id": testboard_id, "settings": {"copper_raise": 0}})
    assert bad.status_code == 400 and "must be > 0" in bad.json()["detail"]
    unknown = client.post("/api/convert", json={"board_id": testboard_id, "settings": {"nope": 1}})
    assert unknown.status_code == 400 and "unknown setting" in unknown.json()["detail"]
    assert client.get(f"/api/jobs/x/files/../../../etc/passwd").status_code == 404


def test_stream_sends_stages_then_the_result(client, testboard_id):
    url = f"/api/convert/stream?board_id={testboard_id}&settings={json.dumps({'base_thickness': 2.4})}"
    with client.stream("GET", url) as r:
        body = "".join(r.iter_text())
    assert body.count("event: stage") == 5 and body.count("event: done") == 1
    payload = json.loads(body.split("event: done\ndata: ")[1].split("\n\n")[0])
    assert payload["build"]["watertight"] and payload["recipe"]["base_thickness"] == 2.4


def test_cors_allows_a_configured_origin(client):
    r = client.get("/api/health", headers={"Origin": "https://example.vercel.app"})
    assert r.headers.get("access-control-allow-origin") in ("*", "https://example.vercel.app")
