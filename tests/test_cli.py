import json

import pytest

from conftest import BADGE, FIXTURES, ROOT
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


def test_out_writes_every_output(tmp_path, capsys):
    assert main([str(FIXTURES / "testboard.kicad_pcb"), "-o", str(tmp_path)]) == 0
    for name in ("board.stl", "board.3mf", "preview.png", "plot_1to1.pdf", "report.json",
                 "layers/outline.svg", "layers/F.Cu.svg", "layers/User.1.svg"):
        assert (tmp_path / name).stat().st_size > 0, name
    assert (tmp_path / "preview.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["build"]["watertight"] and report["build"]["is_volume"]
    assert report["build"]["volume_mm3"] == pytest.approx(report["build"]["volume_formula_mm3"], rel=1e-5)
    assert "KiCad → printable board in" in capsys.readouterr().out


def test_same_input_same_stl(tmp_path):
    for run in ("a", "b"):
        assert main([str(FIXTURES / "testboard.kicad_pcb"), "-o", str(tmp_path / run)]) == 0
    assert (tmp_path / "a" / "board.stl").read_bytes() == (tmp_path / "b" / "board.stl").read_bytes()


def test_pdf_is_true_scale(tmp_path):
    import re
    assert main([str(BADGE), "-o", str(tmp_path)]) == 0
    box = re.search(rb"/MediaBox \[\s*([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+)\s*\]", (tmp_path / "plot_1to1.pdf").read_bytes())
    w_mm, h_mm = (float(box[3]) - float(box[1])) / 72 * 25.4, (float(box[4]) - float(box[2])) / 72 * 25.4
    # 1 mm in the drawing = 1 mm of paper: height = board + 2 × 10 mm margins + 22 mm footer;
    # width = board + margins, but at least 120 mm so the footer text fits
    assert (w_mm, h_mm) == pytest.approx((max(95.025 + 20, 120), 147.34 + 42), abs=0.01)


def test_svg_is_in_millimetres(tmp_path):
    assert main([str(FIXTURES / "testboard.kicad_pcb"), "-o", str(tmp_path)]) == 0
    head = (tmp_path / "layers" / "outline.svg").read_text()
    assert 'width="50.0000mm" height="40.0000mm"' in head and 'viewBox="100.0000 100.0000 50.0000 40.0000"' in head


def test_bad_recipe_exits_1(tmp_path, capsys):
    bad = tmp_path / "bad.yaml"
    bad.write_text("nonsense: 1\n")
    assert main([str(FIXTURES / "testboard.kicad_pcb"), "-o", str(tmp_path / "out"), "--recipe", str(bad)]) == 1
    assert "unknown recipe key" in capsys.readouterr().err


def test_unknown_layer_exits_1(capsys):
    assert main([str(FIXTURES / "testboard.kicad_pcb"), "--summary", "--layer", "In1.Cu"]) == 1


def test_fab_preset_reports_its_effects(tmp_path):
    assert main([str(FIXTURES / "testboard.kicad_pcb"), "-o", str(tmp_path), "--recipe", str(ROOT / "params" / "3dpcb.yaml")]) == 0
    b = json.loads((tmp_path / "report.json").read_text())["build"]
    assert len(b["recipe_effects"]["alignment_holes"]) == 2
    assert b["stl_file_watertight"] and b["volume_mm3"] == pytest.approx(b["volume_formula_mm3"], rel=1e-5)
