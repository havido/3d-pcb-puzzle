# kicad2cad

Turn a KiCad board (`.kicad_pcb`, KiCad 8/9) into a 3D-printable 3DPCB board with the copper raised on top. Plan, tests and hardware checks: [`docs/kicad2cad-plan.md`](../../docs/kicad2cad-plan.md).

**Status:** phases 0–4 done. Next: phase 5 (compare with Adit's hand-made goose) and phase 6 (handoff).

## Setup
```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && pip install -e .
```

## Use
```
kicad2cad "Archive 2/badge.kicad_pcb" --summary          # what was read: outline, copper per layer, pads, drills, warnings
kicad2cad "Archive 2/badge.kicad_pcb" --summary --json   # the same, as JSON
kicad2cad tests/fixtures/testboard.kicad_pcb -o out/testboard --recipe params/3dpcb.yaml   # for printing
```

`-o` writes into the output folder:

| File | What it's for |
|---|---|
| `board.stl`, `board.3mf` | the printable board (mm); open in Bambu Studio |
| `preview.png` | top view as in KiCad, warnings circled in red |
| `plot_1to1.pdf` | print at 100 % for the paper size/mirror check |
| `layers/*.svg` | outline, copper and user layers in mm (on-screen goose map, #16) |
| `report.json` | counts, areas, volume, mesh checks, warnings, file hashes, recipe used |

**Recipe.** Without `--recipe` you get a plain conversion. `params/3dpcb.yaml` is the fabrication preset, and it holds every tunable number:
- copper layer, base thickness, copper height, curve accuracy
- **small drills:** holes narrower than `min_drill` are enlarged, skipped or kept
- **alignment holes:** two holes for the cutter plate's pins, placed automatically clear of copper, holes and the edge (or at positions you give)
- **extra layers:** cut user-layer shapes into the board, e.g. `User.1: {op: recess, depth: 1.5}` for the goose's channels. The ops are `recess`, `pocket` and `through`.

Unknown or invalid recipe values are an error. `report.json` lists what each option changed.

## Test
```
pytest -q                                  # 95 tests, ~10 s
python tests/fixtures/make_testboard.py    # regenerate the synthetic test board after changing it
```
