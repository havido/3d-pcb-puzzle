import json

import pytest

from conftest import BADGE, FIXTURES
from kicad2cad.__main__ import main


def test_summary_text(capsys):
    assert main([str(FIXTURES / "testboard.kicad_pcb"), "--summary"]) == 0
    out = capsys.readouterr().out
    assert "50.0 x 40.0 mm" in out and "warnings  1" in out


def test_summary_json_badge_fast(capsys):
    assert main([str(BADGE), "--summary", "--json"]) == 0
    s = json.loads(capsys.readouterr().out)
    assert s["copper"]["F.Cu"]["segments"] == 634
    assert s["seconds"] < 10


def test_nothing_to_do_errors():
    with pytest.raises(SystemExit):
        main([str(BADGE)])


def test_missing_file_exits_1(capsys, tmp_path):
    assert main([str(tmp_path / "nope.kicad_pcb"), "--summary"]) == 1
    assert "error:" in capsys.readouterr().err


def test_out_writes_preview(tmp_path, capsys):
    assert main([str(FIXTURES / "testboard.kicad_pcb"), "-o", str(tmp_path)]) == 0
    png = tmp_path / "preview.png"
    assert png.exists() and png.stat().st_size > 10_000
    assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_unknown_layer_exits_1(capsys):
    assert main([str(FIXTURES / "testboard.kicad_pcb"), "--summary", "--layer", "In1.Cu"]) == 1
