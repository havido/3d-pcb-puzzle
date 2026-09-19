# kicad2cad

Turn a KiCad board (`.kicad_pcb`, KiCad 8/9) into a 3D-printable 3DPCB board. Plan, tests and hardware checks: [`docs/kicad2cad-plan.md`](../../docs/kicad2cad-plan.md).

**Status:** phases 0–2 done. The tool reads any board, turns it into 2D shapes and draws a preview. Building the 3D board (3MF/STL) comes in phase 3.

## Setup
```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && pip install -e .
```

## Use
```
kicad2cad "Archive 2/badge.kicad_pcb" --summary          # what was read: outline, copper per layer, pads, drills, warnings
kicad2cad "Archive 2/badge.kicad_pcb" --summary --json   # the same, as JSON
kicad2cad "Archive 2/badge.kicad_pcb" -o out/badge       # writes out/badge/preview.png (top view, as in KiCad)
```

## Test
```
pytest -q                                  # 60 tests, ~3 s
python tests/fixtures/make_testboard.py    # regenerate the synthetic test board after changing it
```
