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
    assert s["parse_seconds"] < 10


def test_build_not_implemented_yet():
    with pytest.raises(SystemExit):
        main([str(BADGE)])


def test_missing_file_exits_1(capsys, tmp_path):
    assert main([str(tmp_path / "nope.kicad_pcb"), "--summary"]) == 1
    assert "error:" in capsys.readouterr().err
