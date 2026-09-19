# kicad2cad

Turn a KiCad board (`.kicad_pcb`, KiCad 8/9) into a 3D-printable 3DPCB board with the copper raised on top. Plan, tests and hardware checks: [`docs/kicad2cad-plan.md`](../../docs/kicad2cad-plan.md).

**Status:** phases 0–3 done. Phase 4 adds recipe extras (goose channels, alignment holes, small-drill policy).

## Setup
```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && pip install -e .
```

## Use
```
kicad2cad "Archive 2/badge.kicad_pcb" --summary          # what was read: outline, copper per layer, pads, drills, warnings
kicad2cad "Archive 2/badge.kicad_pcb" --summary --json   # the same, as JSON
kicad2cad tests/fixtures/testboard.kicad_pcb -o out/testboard --recipe params/3dpcb.yaml
```

`-o` writes into the output folder:

| File | What it's for |
|---|---|
| `board.stl`, `board.3mf` | the printable board (mm); open in Bambu Studio |
| `preview.png` | top view as in KiCad, warnings circled in red |
| `plot_1to1.pdf` | print at 100 % for the paper size/mirror check |
| `layers/*.svg` | outline, copper and user layers in mm (on-screen goose map, #16) |
| `report.json` | counts, areas, volume, mesh checks, warnings, file hashes, recipe used |

Every tunable number is in the recipe (`params/3dpcb.yaml`): copper layer, base thickness, copper height, curve accuracy.

## Test
```
pytest -q                                  # 75 tests, ~7 s
python tests/fixtures/make_testboard.py    # regenerate the synthetic test board after changing it
```
