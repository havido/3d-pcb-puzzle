# 3DPCB

3D-printed, copper-tape circuit boards: a middle ground between perfboard and a fabbed PCB — neat prototypes without killing project momentum. Core pipeline: **KiCad file → 3D-printable board model → copper tape applied and cut → parts soldered.**

Built at Hack the North (Waterloo, 36 h, started 2026-09-19). Optimise for a working demo, not polish.

## Current goal: goose-shaped "Operation" game for the hacker badge (chosen 2026-09-19)

The demo 3DPCB is a goose-shaped board played like the Operation game, with the event's hacker badge as its brain and screen.

- The goose has maze-like channels. The player moves an "organ" out through one channel and brings another organ in through a different one, against a countdown.
- **Sensing is pure copper, no components needed:** the tweezers/organ are tethered to badge GND; copper zones on the goose each go to one badge button line (active-low, 10k pull-ups already on the badge). Touching a wall = that "button" pressed = seconds knocked off the timer. Seat pads detect organ removed / organ delivered the same way.
- The badge app keeps the timer, animates success/failure on the display, and flashes the LEDs. Contact to the badge is by pogo pins on exposed button pads + the GND test point (TP4).
- **Verified on a real badge (2026-09-19):** on every tact switch the two pads nearer the display are GND and the two nearer the bottom edge are the button signal (2.3 × 1.5 mm pads, 4.5 mm apart vertically, 9.1 mm horizontally). Jumpering them registers as a press. So GND is available at every button — TP4 is not needed. Signal pad centres (KiCad mm): BTN_2/SW2 up (73.8 | 82.9, 123.4); BTN_4/SW4 left (67.0 | 76.0, 131.0); BTN_3/SW3 right (80.5 | 89.6, 131.0); BTN_5/SW8 down (74.4 | 83.5, 138.8); GND pads are 4.5 mm above each (smaller y).
- **Fabrication design (2026-09-19, supersedes the feather-island idea):** traces are 3 mm raised lands (1.0 mm tall) on the plate (4.0 mm now, see tray note). Every trace is ringed by a 1.5 mm moat (0.6 deep) and a 0.8 x 0.4 mm shear rim. The cutter plate has 3.4 mm grooves over the traces and 1.2 mm teeth that drop into the moats: the tooth wipes the tape down the trace sidewall (0.2 mm gap = tape + 0.1) and shears it against the rim (0.10 mm gap - the number to tune on a coupon). Where two different nets share a moat (copper gap 3 mm) nothing shears: score the moat floor with a knife. Cutter locates on the board with 3 x 5.0 mm pins in 5.2 mm sockets and has two pry scoops. Back copper sits in 0.4 mm recesses. Holes: pogo 1.18 mm (press fit, P75), vias 2.4 mm (M2 screw / wire / tape tail).
- **Badge tray (separate print, lips on the bed, no supports, NO GLUE anywhere - user rule: press fits or slide-to-lock only).** Two styles from `kicad2fab.py --style`:
  - `clamshell` (default): badge drops onto two dowels through its bottom corner holes (4.45 mm holes; one round 4.30 dowel = X+Y, one relieved "diamond" dowel = rotation only), rests on lips under its back (Z), 0.3 mm clearance to the walls. Then the board goes on top. Pogo pins meet the badge vertically - nothing drags across it.
  - `slide`: badge slides in from its top end; two pads on one long edge + one end stop + a printed spring finger; slides in ~0.7 mm below the pogo tips, then two 1.9 mm shim strips lift it onto the pins.
  - Tray-to-board lock (both styles, no glue): two 6.0 mm posts on the tray (tail end) pass through 6.2 mm holes in the board, a 2.2 x 1.8 mm key slides through each post above a raised boss; plus one printed C-clip slid over the board edge and into a notch in the tray bottom at the head-top edge (the only straight copper-free edge over a tray wall; jaw bite is only 2.0 mm because v3 has ~2.4 mm of bare margin there). The script places the clip where lift at the pogo pins per mm of hold-down play is lowest (1.2 on v3; the old three-post layout was ~3.6). Plate stays 4.0 mm. Tray footprint 76 x 105 mm (was 92 x 111): walls 5 mm, rails start at portrait Y 118, ears reach 7 mm. Next KiCad revision: leave >= 4 mm bare margin at the clip and a copper-free spot over each rail near the D-pad.
  - Buttons: board back is 5.5 mm above the badge face, tact switches are 5.0 tall. Every covered button (SW2, SW3, SW4, SW5, SW8, SW10 on v3) gets a 5.0 mm x 1.0 mm relief pocket in the board back -> 1.5 mm of air, so the board can never hold a D-pad line down. Open buttons (`--open`, SW6 = start, SW7) get a captive printed plunger because the button top sits ~4.5 mm below the play surface. Checked: the four pogo holes are centred on their pads (PENALTY->SW3/BTN_3, GOAL_1->SW2/BTN_2, GOAL_2->SW4/BTN_4, GND->SW8 GND pad), 0.7 mm margin in the pad's narrow (1.5 mm) direction; estimated stack-up error ~0.4 mm. Set pogo tips 6.2 mm below the board back with the printed pin gauge (~1.2 mm compression).
  - 10 uF cap from PENALTY to GND still applies; app ignores buttons for 0.5 s after boot and uses a touch lockout.
- **Circuit (final, 2026-09-19): 4 nets, 4 pogo pins.** PENALTY = both penalty traces joined → BTN_2 (SW2 signal pad, 73.8 or 82.9, 123.4), with the 10 µF cap. GOAL_1 → BTN_4 (SW4, 67.0, 131.0). GOAL_2 → BTN_3 (SW3, 89.6, 131.0). GND → upper-right pad of SW8 (83.5, 134.2) → tweezers tether (moved off SW2 so all four 3 mm vias keep ≥ 3 mm clearance). BTN_5 spare. The A button stays exposed through a cut-out and starts the game. Never use ESP32_BOOT (SW10).
- **Goose layout (user's drawing, `goose/goose_landscape.kicad_pcb`, badge rotated a quarter turn, top on the left):** penalty trace 1 = head/neck/back line; penalty trace 2 = breast/belly/body line (both → PENALTY); GOAL_1 = tail loop; GOAL_2 = belly loop near the D-pad. Traces are plain tracks (not feather islands). Drawing targets: 3 mm tracks, ≥ 3 mm between different nets, corridor ≥ 10 mm, 45° corners, outline on Edge.Cuts ≥ 4 mm outside copper, keep A/B clear. Convert with `--ref-turns 1`.
- **Current board = `goose/goose_landscape_v3.kicad_pcb` (+ `.fs`), 158 × 133 mm plate.** Button mapping as actually wired there (supersedes the "Circuit" bullet): **PENALTY → BTN_3 (D-pad right, SW3)**, **GOAL_1 (tail loop) → BTN_2 (D-pad up, SW2)**, **GOAL_2 (belly loop) → BTN_4 (D-pad left, SW4)**, GND → SW8 upper pad. Penalty trace 2 and the tail reach their pins through back-copper (B.Cu) tracks + vias. Plate cut-outs exist for SW6 (SW_HPM — use it as the start button) and SW7 (Home); SW5 sits under the neck trace and is covered. KiCad DRC: no clearance or unconnected errors at 3 mm / 3 mm.
- **Game rules (in the app):** A starts a countdown; each PENALTY touch subtracts seconds (with ~0.5 s lockout); win = GOAL_1 then GOAL_2, in that order, before time runs out; GOAL_2 before GOAL_1 does not count. Difficulty comes from time pressure — start time and penalty size are constants to tune by playtesting.
- Earlier ideas (optical input from the LEDs, diode ROM, rotor cipher) are parked in `CONTEXT.md`; optional easter eggs only.

Priorities, in order:
1. Verify on a real badge: jumper a button pad to GND, confirm an app sees it; then the same through copper tape + tweezers (are brief touches caught?).
2. Test coupon: channel width vs organ size, copper on channel edges, tape adhesion, sandwich-cutter clearance.
3. Goose board: KiCad outline + zones → 3D model generator → print, tape, wire.
4. Badge dock (registers on the badge outline, carries pogo pins) and tweezers tether.
5. Badge app: timer, touch penalties, stage logic, animations.
6. Robotic assembly (the old plan) — only if everything above is done.

## Hard constraints

- **The badge is irreplaceable.** Nothing that risks it: no solder-mask peeling, no soldering to it, battery switch OFF before USB. Contact only exposed pads (button solder joints 2.3 × 1.5 mm, 1.5 mm test points).
- **The badge has no spare GPIO.** It has no drilled mounting holes, but Edge.Cuts has four routed Ø 4.45 mm corner holes (see `CONTEXT.md` A2) — the clamshell tray's dowels use the bottom two; otherwise register on the board outline (~95 × 147 mm, 1.6 mm thick).
- **Board design rules:** single-sided, wide traces (start at ~2 mm; the coupon test sets the real minimum), holes ≥ 1 mm, few parts, low voltage. Two layers only if the puzzle needs it.
- **Fabrication:** printed positive/negative sandwich — raised traces on one plate, matching recesses on the other, clearance for the copper thickness, alignment pins, pry slots — shears the tape at trace edges. Known risk: printed edges crush instead of cut, so clearance is a parameter to tune, not a constant. Fallback: recessed traces + ridges + wet abrasion (`PLAN.md`).
- No epoxy; no dry sanding (dust). Solder is Sn42Bi58 with the iron at 200–220 °C, on PETG.
- Printers are venue Bambu A1s, first come first served, 0.4 mm nozzle, PETG/PLA. Print time is the bottleneck — minimise the number and size of per-board prints.
- One mechatronics person (Adit); the three teammates are software-only. Keep hardware steps simple and software parametric — every dimension that might need tuning (trace width, clearance, plate thickness, pin size) is a named parameter, not a literal.

## Printer tolerances (Bambu A1 mini, 0.4 nozzle, 180 mm bed) - researched guide, not yet measured on our printer

| Feature | CAD value |
|---|---|
| Shrinkage | set filament shrinkage 100.3 % PLA / 100.4 % PETG; leave XY and hole compensation at 0, do offsets in CAD |
| Small holes print 0.15-0.25 small | P75 pogo press fit 1.18, slip fit 1.30 |
| Mating parts, per side | press 0-0.05, snug 0.05-0.10 (PETG +0.05), loose 0.15-0.25 |
| Groove over a 3 mm taped ridge | 3.40 |
| 1.6 mm PCB | slide slot 2.10; drop-in outline +0.25-0.35 per side |
| Elephant foot | 0.10 slicer compensation + 0.5 mm chamfer on mating bottom edges |
| Minimums | wall 0.8 (1.2 better), raised feature 0.4 tall at 0.2 layers, gap between ridges 0.5 |
| Alignment pins 3-5 mm | socket = pin + 0.2, 1-1.5 mm lead-in |
| Large thin plate | bed 65 PLA / 80 PETG, 5-10 mm brim, gyroid 15-20 %, 3 walls, fan off first 3 layers |
| Tape surface | monotonic top, 5-6 top layers, ironing 30 mm/s, 15-20 % flow, 0.15 spacing |
| Slicer | Arachne, outer/inner wall order, outer wall 50 mm/s, precise Z height, aligned seam, arc fitting |

## Where things are

| Path | What |
|---|---|
| `CONTEXT.md` | Full context: badge pin map, LED / button / test-point coordinates, interface options, puzzle ideas, and the old robot-assembly plan. Read section A before touching anything badge-related. |
| `Archive 2/` | Badge KiCad 9 project (`badge.kicad_pcb`, `badge.kicad_sch`) — read-only reference from the organisers. [Interactive BOM](https://hackathon.github.io/badge-hardware/badge-ibom.html). |
| `tools/kicad2fs.py` | KiCad `.kicad_pcb` → Onshape FeatureScript (needs `shapely`). Layer convention: Edge.Cuts = outline + cut-outs, F.Cu = raised feathers, B.Cu = back copper, User.1 = seat pockets, drills/vias = through holes, Dwgs.User ignored. `--ref` adds the badge as a reference sketch. Workflow is KiCad → FeatureScript → manual CAD in Onshape for the badge fit. FeatureScript output not yet verified inside Onshape. |
| `tools/kicad2fab.py` | **Main generator.** KiCad board + badge PCB -> one FeatureScript (`*_fab.fs`, feature "3DPCB fab set") with bodies board, cutter, tray, keys (+ shim for `--style slide`); output is `*_fab_<style>.fs`. Every fit is a named value in `P` at the top; edit and re-run. `--turns` must match the template, `--open SWn` adds finger holes, `--preview x.png` draws a check image. FeatureScript not yet verified inside Onshape. |
| `tools/make_goose_template.py` | Builds the drawing template (first one is now `goose/history/goose.kicad_pcb`): blank board with the badge traced on Dwgs.User, in badge coordinates. Draw the goose in this file. |
| `README.md` | Public overview + quick start for teammates. |
| `docs/PIPELINE.md` | How `kicad2fab.py` works (data flow, 2D constructions, the `Ops` IR), what is hard-wired to the goose/badge, and the full generalisation roadmap. |
| `goose/` | Current board `goose_landscape_v3.*` + generated `.fs` / previews; `goose/history/` = older drawings, nothing depends on them. |
| `tools/scale_tracks.py` | Scales all tracks about a point and sets their width. |
| `PLAN.md` | Old robot-assembly plan (SO-101 arm). Low priority; still the reference for the recessed-trace fallback process. |
| `RESEARCH_PROMPTS.md` | Research prompts behind `PLAN.md`. |

## Next: generalise the KiCad -> STL pipeline (teammates, from 2026-09-19)

Two generators exist; do not grow both. **`tools/kicad2cad`** (havido, branch `feat/kicad2cad`, plan in `docs/kicad2cad-plan.md`) is the general tool: full KiCad parser with nets, typed `Board2D`, watertight STL/3MF, YAML recipe (`params/3dpcb.yaml`), pytest + CI - but it only makes a plain raised-copper board. **`tools/kicad2fab.py`** (Adit) holds the fabrication know-how - moat, shear rim, cutter, badge tray - but reads only tracks + vias and outputs FeatureScript. The work is to port the second into the first. Details for every item: `docs/PIPELINE.md` section 4; keep the two in sync.

1. **Port moat / shear rim / cutter into kicad2cad** as recipe options + a `cutter` body (#29, #15). `docs/PIPELINE.md` section 2 is the spec; carry over `solidify()`, `clean()`, `STEP`, `EPS`. Reconcile defaults (kicad2cad base 2.0 / copper 0.6 / 3 mm holes vs kicad2fab plate 4.0 / trace 1.0 / 5.0 pins in 5.2 sockets). Acceptance: goose v3 matches the kicad2fab board within 0.2 mm (plan item H-D).
2. **Trace-spacing fixer (Adit's idea, fits #31).** Different-net copper closer than `2 x (MOAT_W + RIM_W)` = 4.6 mm (~5 mm) shares a moat and is not sheared. In order: report it (report.json + preview) and ship a KiCad custom DRC rule; adaptive moat / centre ridge with a split tooth for 3-4.6 mm gaps; push tracks apart and write a *new* `.kicad_pcb` for review (never change geometry silently).
3. **Docking module as an optional add-on:** tray, lock posts, clip, relief pockets, plungers, pin gauge, driven by a per-host file (pogo positions, obstacle footprints, rotation, tray extents). Hard-wired today: `BADGE_CENTRE`, `PINS_PORTRAIT` (duplicated in `make_goose_template.PINS`), the `SWn`/`SW-SMD` switch scan, `TRAY_START_Y` / `LOCATOR_Y` / `SPRING_Y`.
4. **Components:** through-hole pad = land + lead-sized hole, SMD pad = land.
5. **Design checks before generating (#31):** min width / gap / hole, copper-to-edge margin, bed size (dovetailed tiles above 180 mm), no room for pins/posts. Report coordinates.
6. **Coupon generator (#10)** sweeping trace width, gap and shear clearance; measured values replace the recipe defaults and the guesses in this file.
7. **Auto-widen thin tracks** (`min_track_width`), reporting where neighbours block it.
8. **Tests:** goose v3 as a second fixture; property checks (teeth never intersect the groove, holes inside the plate, no touching regions).
9. Later: back-side cutter, knife-scoring guide for shared moats, embossed net labels, F.Fab part pockets, web UI, keep a CAD (FeatureScript/STEP) export.

Rules for this work: every dimension stays a named parameter; changes to `kicad2fab.py` must leave the goose v3 `.fs` outputs unchanged unless the change is the point (diff them); no GUI dependencies; do not rename or edit `Archive 2/` (organisers' files, and the kicad2cad tests use that path).

## Working notes

- KiCad files are S-expressions, units mm, Y axis points down. Badge coordinates quoted in `CONTEXT.md` are raw KiCad coordinates (board spans x 55.9–150.9, y 29.9–177.3); mirror Y when generating 3D models.
- GPIO numbers in `CONTEXT.md` are inferred from the ESP32-C3-MINI-1 pinout — verify against the schematic before relying on one.
- Prefer open-source, scriptable tools the software teammates can run without a GUI (e.g. Python + CadQuery/OpenSCAD, `kiutils` or a plain S-expression parser). Output STL/3MF.
- When a decision is made (puzzle chosen, minimum trace width measured, clearance that works), update this file and `CONTEXT.md` — measured values replace the guesses above.
