# kicad2cad

Turn a KiCad board (`.kicad_pcb`, KiCad 8/9) into a 3D-printable 3DPCB board. Plan, tests and hardware checks: [`docs/kicad2cad-plan.md`](../../docs/kicad2cad-plan.md).

**Status:** phases 0–1 done. The tool reads any board and reports what it found. Building the 3D board comes in phases 2–3.

## Setup
```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && pip install -e .
```

## Use
```
kicad2cad "Archive 2/badge.kicad_pcb" --summary          # what was read: outline, copper per layer, pads, drills, warnings
kicad2cad "Archive 2/badge.kicad_pcb" --summary --json   # the same, as JSON
```

## Test
```
pytest -q                                  # 42 tests, ~2 s
python tests/fixtures/make_testboard.py    # regenerate the synthetic test board after changing it
```
