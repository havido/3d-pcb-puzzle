# 3DPCB

3D-printed, copper-tape circuit boards: a middle ground between perfboard and a fabbed PCB — neat prototypes without killing project momentum. Core pipeline: **KiCad file → 3D-printable board model → copper tape applied and cut → parts soldered.**

Built at Hack the North (Waterloo, 36 h, started 2026-09-19). Optimise for a working demo, not polish.

## Current goal: goose-shaped "Operation" game for the hacker badge (chosen 2026-09-19)

The demo 3DPCB is a goose-shaped board played like the Operation game, with the event's hacker badge as its brain and screen.

- The goose has maze-like channels. The player moves an "organ" out through one channel and brings another organ in through a different one, against a countdown.
- **Sensing is pure copper, no components needed:** the tweezers/organ are tethered to badge GND; copper zones on the goose each go to one badge button line (active-low, 10k pull-ups already on the badge). Touching a wall = that "button" pressed = seconds knocked off the timer. Seat pads detect organ removed / organ delivered the same way.
- The badge app keeps the timer, animates success/failure on the display, and flashes the LEDs. Contact to the badge is by pogo pins on exposed button pads + the GND test point (TP4).
- Lines for the board: D-pad (BTN_2–5). Keep A/B/Home free for the player. Never use ESP32_BOOT (SW10).
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
- **The badge has no spare GPIO** and no mounting holes — a dock must register on the board outline (~95 × 147 mm, 1.6 mm thick).
- **Board design rules:** single-sided, wide traces (start at ~2 mm; the coupon test sets the real minimum), holes ≥ 1 mm, few parts, low voltage. Two layers only if the puzzle needs it.
- **Fabrication:** printed positive/negative sandwich — raised traces on one plate, matching recesses on the other, clearance for the copper thickness, alignment pins, pry slots — shears the tape at trace edges. Known risk: printed edges crush instead of cut, so clearance is a parameter to tune, not a constant. Fallback: recessed traces + ridges + wet abrasion (`PLAN.md`).
- No epoxy; no dry sanding (dust). Solder is Sn42Bi58 with the iron at 200–220 °C, on PETG.
- Printers are venue Bambu A1s, first come first served, 0.4 mm nozzle, PETG/PLA. Print time is the bottleneck — minimise the number and size of per-board prints.
- One mechatronics person (Adit); the three teammates are software-only. Keep hardware steps simple and software parametric — every dimension that might need tuning (trace width, clearance, plate thickness, pin size) is a named parameter, not a literal.

## Where things are

| Path | What |
|---|---|
| `CONTEXT.md` | Full context: badge pin map, LED / button / test-point coordinates, interface options, puzzle ideas, and the old robot-assembly plan. Read section A before touching anything badge-related. |
| `Archive 2/` | Badge KiCad 9 project (`badge.kicad_pcb`, `badge.kicad_sch`) — read-only reference from the organisers. [Interactive BOM](https://hackathon.github.io/badge-hardware/badge-ibom.html). |
| `PLAN.md` | Old robot-assembly plan (SO-101 arm). Low priority; still the reference for the recessed-trace fallback process. |
| `RESEARCH_PROMPTS.md` | Research prompts behind `PLAN.md`. |

## Working notes

- KiCad files are S-expressions, units mm, Y axis points down. Badge coordinates quoted in `CONTEXT.md` are raw KiCad coordinates (board spans x 55.9–150.9, y 29.9–177.3); mirror Y when generating 3D models.
- GPIO numbers in `CONTEXT.md` are inferred from the ESP32-C3-MINI-1 pinout — verify against the schematic before relying on one.
- Prefer open-source, scriptable tools the software teammates can run without a GUI (e.g. Python + CadQuery/OpenSCAD, `kiutils` or a plain S-expression parser). Output STL/3MF.
- When a decision is made (puzzle chosen, minimum trace width measured, clearance that works), update this file and `CONTEXT.md` — measured values replace the guesses above.
