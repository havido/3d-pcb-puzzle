# Goose board (the demo)

| File | What |
|---|---|
| `goose_landscape_v3.kicad_pcb` / `.kicad_pro` | **Current board.** 158 x 133 mm, badge rotated a quarter turn (`--turns 1`). Nets: PENALTY, GOAL_1, GOAL_2, GND. |
| `goose_landscape_v3_fab_clamshell.fs` / `_slide.fs` | Generated fab sets (`tools/kicad2fab.py`). Paste into an Onshape Feature Studio. |
| `goose_landscape_v3_fab_*.png` | `--preview` check images for the two tray styles. |
| `goose_landscape_v3.fs` | Plain board only (`tools/kicad2fs.py`). |
| `history/` | Earlier drawings (portrait template, x2 scale test, landscape v1/v2). Kept for reference; nothing depends on them. |

Regenerate everything:

```bash
python tools/kicad2fab.py goose/goose_landscape_v3.kicad_pcb --badge "Archive 2/badge.kicad_pcb" --turns 1 --open SW6 SW7 --preview goose/goose_landscape_v3_fab_clamshell.png
python tools/kicad2fab.py goose/goose_landscape_v3.kicad_pcb --badge "Archive 2/badge.kicad_pcb" --turns 1 --open SW6 SW7 --style slide --preview goose/goose_landscape_v3_fab_slide.png
python tools/kicad2fs.py  goose/goose_landscape_v3.kicad_pcb --ref "Archive 2/badge.kicad_pcb" --ref-turns 1
```
