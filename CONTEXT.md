# 3DPCB Hackathon Project — Context Dump

> **READ THIS FIRST — pivot as of 2026-09-19 (hackathon under way, Hack the North, Waterloo).**
> Section "A" below is the current plan. Everything from "Background" onward is the older robot-assembly plan (see also `PLAN.md`, `RESEARCH_PROMPTS.md`). **Robotic assembly is now LOW priority** — only picked up if the puzzle is finished early. The KiCad → 3D-printable board conversion and the copper-tape fabrication process are still core.

## A. Current plan: the 3DPCB is a puzzle that plugs into the hacker badge

### A1. Concept
- Fabricate a 3D-printed copper-tape PCB ("3DPCB") that **encodes a puzzle**. It docks onto the event's hacker badge, and the badge is the tool used to solve it.
- **Badge → puzzle:** the badge's RGB LEDs are the input to the puzzle.
- **Puzzle → badge:** puzzle outputs feed back into the badge through a suitable electrical spot on the badge PCB (candidates in A3).
- A badge app (apps are user-writable: badge.hackthenorth.com; badge workshop Sat 11:30 AM) drives the LEDs and reads the result.
- **Open item:** choose a puzzle that is simple enough to fabricate on a wide-trace, single-sided copper-tape board, but unique enough to justify hardware instead of "just a firmware app". The puzzle's logic should live physically in the copper (the routing IS the secret), not in code.

### A2. Badge facts (from `Archive 2/`: `badge.kicad_pcb`, `badge.kicad_sch`, KiCad 9 format, "Hacker Badge V1.1.1, 28/06/2026")
Repo name `badge-hardware`; interactive BOM: https://hackathon.github.io/badge-hardware/badge-ibom.html. A zip backup of the same files is in `Archive 2/badge-backups/`.
- **Board:** 2-layer, 1.6 mm, outline about 95 × 147 mm (KiCad coords x 55.9–150.9, y 29.9–177.3). Has V-cut markings. Largest drill is 1.98 mm, but Edge.Cuts has **4 routed round holes, Ø 4.45 mm**, centres (74.58, 33.79), (132.28, 33.82), (74.59, 173.21), (132.29, 173.24) — ~3.9 mm in from the edge, on a 57.7 × 139.4 mm rectangle. A dock can locate on these with printed pins instead of the outline (confirm on the real badge that they're open and not needed for the lanyard).
- **MCU:** U9 ESP32-C3-MINI-1-N4. **Every usable GPIO is taken; there is no spare pin.**
  | Module pin (GPIO) | Net |
  |---|---|
  | 5 (IO2) | DISP_CS |
  | 6 (IO3) | LED_DIN_3V3 → U11 level shifter → LED_DIN → R3 100 Ω → LED1 |
  | 12 (IO0) | DISP_RS |
  | 13 (IO1) | DISP_SCL |
  | 16 (IO10) | DISP_SDA |
  | 18 (IO4) | DISP_RST |
  | 19 (IO5) | I2C_SDA_BUS |
  | 20 (IO6) | I2C_SCL_BUS |
  | 21 (IO7) | SR_QH (button shift register data) |
  | 22 (IO8) | 10k pull-up only |
  | 23 (IO9) | ESP32_BOOT (SW10 to GND, 10k pull-up) |
  | 26/27 (IO18/19) | USB D−/D+ via R40/R41 |
  | 30 (IO20) | SR_SHLD |
  | 31 (IO21) | SR_CLK |
  (GPIO numbers verified against the schematic's ESP32-C3-MINI-1 symbol, 2026-09-19. Pins 30/31 are RXD0/TXD0 = IO20/IO21.)
- **LEDs:** 6× WS2812B-2020 on the **front**, one daisy chain LED1→LED6, powered from +5V. Positions (KiCad mm): LED1 (65.9, 37.9), LED2 (137.1, 37.7), LED3 (131.4, 106.3), LED4 (129.4, 164.6), LED5 (71.8, 163.8), LED6 (72.1, 106.9) — roughly the four corners plus mid-left and mid-right. **LED6 data-out pad is unconnected** (0.9 × 0.7 mm pad).
- **Buttons:** 7 tact switches (KH-6X6X5H, front) + slide switch SW11 feed U8 74HC165 shift register. All are **active-low with 10k pull-ups to 3V3**; switch pads are big exposed solder joints (2.3 × 1.5 mm).
  - BTN_1 = SW11 slide; BTN_2 = SW2 (78.4,121.2); BTN_3 = SW3 (85.1,128.7); BTN_4 = SW4 (71.5,128.7); BTN_5 = SW8 (79.0,136.5) — these four are the D-pad on the left.
  - BTN_7 = SW5 (121.4,130.9); SW_HPM = SW6 (135.9,124.3) — A/B on the right. BTN_6 = SW7 (97.5,150.0) and ESP32_BOOT = SW10 (112.0,149.9) — Home/Start at the bottom. (Which is which to be confirmed on the real badge.)
  - Verified from `badge.kicad_pcb`: every tact switch has its **two GND pads on one side and two signal pads on the other** (4.5 mm apart vertically, 9.1 mm horizontally; for rotation 0 the GND pads are the upper row). A puzzle output needs only two pogos on the same switch (signal + GND) — no separate GND contact.
  - U8 74HC165 runs from +3V3; inputs D0–D7 = BTN_1…BTN_7, SW_HPM. SW_HPM is electrically an ordinary button; its name may mean special firmware handling — check before using it.
  - **SW10 / ESP32_BOOT goes straight to IO9, a strapping pin: never use it as a puzzle output** (held low at reset = firmware-download mode).
- **I2C bus (IO5/IO6, pull-ups R34/R36):** U2 SC7A20H accelerometer (front, INT pins unconnected) and U7 MFRC522B NFC reader (back). The NFC reader is what scans the venue stickers; its antenna is at the bottom of the badge, inside a keep-out area x 77.7–129.8, y 142.5–175.2 (both layers). Keep puzzle copper out of that area, or NFC is detuned while docked. TP6 (back) = NFC IRQ.
- **Test points (1.5 mm round, front unless noted):** TP1 VBUS (73.1, 91.4), TP3 +5V (79.1, 103.9), TP4 GND (58.2, 74.8), TP5 +3V3 (88.2, 99.4), TP6 NFC IRQ (62.1, 125.7, back). **No signal test points exist.**
- **Power:** 2× AA holder on the back → Q1 AO3401 reverse protection → SW1 power slide → U4 MT3608 boost to +5V → U5 XC6220 3.3 V LDO. U12 LM66200 selects between VBUS and boosted battery. JP1 = open solder jumper (back) that bypasses Q1. USB-C with SRV05 ESD protection, native USB to the ESP32-C3. Display on a 12-pin FPC (SPI-style).
- **Badge rules that matter:** no replacements if damaged; turn the battery switch OFF before plugging in USB; low batteries cause glitches; warm near USB/top/back = turn off.

### A3. Interface options (ranked)
**Badge → puzzle (outputs of the badge)**
1. **Optical, from the 6 LEDs** (user's preferred idea): the puzzle board carries light sensors (LDRs / phototransistors) sitting over LED positions, with printed light shrouds. Zero electrical connection, zero risk to the badge, and it uses colour + position as the input alphabet. LED pitch is large (tens of mm), which suits wide copper-tape traces.
2. LED6 DO pad: the WS2812 chain could be extended onto the puzzle board (more pixels on the puzzle). Needs a pogo on a 0.9 × 0.7 mm pad — fiddly.
3. +5V / +3V3 / GND test points (TP3, TP5, TP4) to **power the puzzle from the badge** — 1.5 mm pads, easy pogo targets, no solder mask to remove.

**Puzzle → badge (inputs to the badge)**
1. **Button lines (recommended):** pull a BTN_x pad to GND and the badge sees a button press. Pads are exposed solder on the front, 10k pull-ups already present, fully passive, and readable by any badge app with no firmware changes to low-level drivers. A puzzle output is just "a transistor or a copper path to GND". **No solder-mask peeling needed.** Cost: that physical button is shadowed while docked (pick ones the puzzle app doesn't need).
2. I2C bus: would need the puzzle to have an MCU acting as an I2C device, and pads are tiny (R34/R36 ends). Against the "logic lives in copper" spirit.
3. USB-C: needs an MCU on the puzzle. Same objection.
4. NFC: a bare copper-tape coil is not a tag; would need an NFC chip. Possible stretch ("puzzle unlocks a tag"), not the main path.
5. Accelerometer (tilt/shake as input): firmware-only, no contact — possible flavour, not a data path.
- Solder-mask peeling (custom jig + flat-head screwdriver) is only needed if we insist on a net that has no exposed pad. With button pads + test points it should be avoidable. Risky on a non-replaceable badge.

### A4. Puzzle ideas (open item — none chosen yet)
The constraint: few parts, wide traces, single-sided (or 2-layer sandwich), and the secret should be physically in the routing.
- **Hidden-wiring maze / "cut the right wire":** the board's routing between sensor nodes and button lines is hidden under a cover. The player sets LED colours/positions in the badge app; only the right pattern drives the right sensors and the board "presses" a button sequence back. Different printed boards = different puzzles, so puzzles become swappable physical cartridges — this is the argument against "just firmware", and it ties into the KiCad → 3DPCB generator (generate a new puzzle cartridge per person).
- **Colour-filter logic:** coloured filament/gel windows over the sensors make each sensor respond to only one colour; diode/transistor AND-OR logic in copper decides the output.
- **Multilayer reveal:** the solution path crosses layers, which justifies trying a 2-layer 3DPCB.
- **Analog ladder:** sensors switch resistors into a divider; only one LED combination hits the threshold that triggers the output transistor.

### A5. Fabrication approach (updated by user 2026-09-19)
- For a simple low-voltage circuit, **trace width / copper adhesion is the deciding variable**, not the electrical physics.
- **Test print:** a coupon with a range of trace widths (and gaps) to find the narrowest trace the copper tape stays stuck to after cutting/handling/soldering.
- **Cutting mechanism under strong consideration: positive + negative sandwich.** Two printed plates (one with raised traces, one with matching recesses) with an **offset/clearance at the traces to accommodate the copper thickness**; pressing them together shears the tape at the trace edges. **Alignment pins and slots**, plus pry slots to get them apart again.
  - Known risk from the Hackaday comments: printed plastic edges crush rather than cut; clearance tuning is the experiment. Fallback: recessed traces + ridges + wet abrasion (see `PLAN.md`).
- **Multilayer** is a nice-to-have, only if the chosen puzzle needs it (stack of plates, pins/solder through aligned holes for vias).
- If probing points can't be used for badge input, a **mask-peeling jig** is the contingency (see A3).

### A6. Priorities now
1. Pick the puzzle (A4) and lock the badge interface (A3) — verify button-pad injection on a real badge with a jumper wire to GND first.
2. Trace-width coupon + sandwich-cutter test.
3. KiCad → 3D model generator for the puzzle board + printed dock that registers on the badge outline and carries pogo pins / light shrouds.
4. Badge app (LED patterns out, button-line reads in).
5. Robotic assembly (old plan below) — only if time remains.

---
# (Older plan, kept for reference — robot assembly now low priority)

## Background
- Inspiration: Hackaday articles on 3D-printed PCBs with copper tape:
  - Raccoon Lab (May 2026): traces 2 mm wide, raised, copper tape applied, then trimmed by hand.
  - QWZ Labs (Jan 2026): KiCad → STEP → Fusion; traces raised 0.6 mm; Arachne wall generator; holes ≥ 1 mm; PLA.
  - PCB Forge by castpixel (Feb 2026): recessed traces with ridges, a matching press piece pushes tape into the grooves, then sanding. Traces down to 0.5 mm; holes need about 1 mm; PETG.
- Main criticisms in the comments: melting when soldering, adhesive failing under heat, peeling off the excess tape is tedious, perfboard or etching is faster.
  - Ideas from the comments: recessed traces plus sanding, drag knife / vinyl cutter, carbide scribing, electroplating, conductive ink.

## Goal
A 48-hour hackathon project that reduces PCB lead time and cost for indie hobbyists.
- Pipeline: KiCad file → 3D-printable board → a robot applies and trims the copper tape → pick-and-place → soldering.
- Pitch: "KiCad file in → working board out in about 30 minutes for about $1", shown with a live timer.
- The judges should wonder how it was done in one weekend.

## Team and constraints
- The user is the only mechatronics person; the 3 teammates are software-only.
- Keep the hardware software-friendly and use open-source tools where they fit.
- 48-hour hackathon. The user's **Bambu P1S is available only on the prep day (2026-09-18), for printing. It is NOT at the hackathon.**
- Venue 3D printers are first come, first served. Pre-print everything generic, so that at the venue only the per-board prints are needed.
- A CNC was ruled out as too expensive; keep costs low. Ask the venue what they have: robot arms, printers that could be lent as robots, vinyl cutters or Cricuts, laser cutters.
- Do not drop any pipeline step. Rank the steps by feasibility, each with a fallback.

## Core concept: precision lives in printed jigs, not the robot
- The robot is an **SO-101 arm (LeRobot)**, printed on the P1S on the prep day. Its precision is roughly millimetre-level, so it can't trace cuts accurately.
- The software generates **per-board jigs from the KiCad file**, printed on venue printers:
  - the board, with **recessed** traces (PCB Forge style) and ridges
  - a matching press piece
  - a paste stencil
  - part nests (funnel-shaped pockets)
  - a bed-of-nails test fixture (pogo pins at every test point)
- A fixed, printed base plate holds every jig in a known position, so the arm can repeat fixed poses without needing vision.
- The arm uses tools with **printed handles**, picked from a tool rack: roller, press pusher, sanding block, squeegee. A vacuum cup on the wrist handles pick-and-place.

### Process
1. A human drops the tape sheet (backing removed) against a corner stop. Stretch goal: the arm peels the backing and lays the sheet.
2. The arm rolls the tape, then presses the press piece down to push the tape into the grooves.
3. The arm sands with a scrubbing motion (tolerant of imprecision), removing copper from the ridges so the traces are isolated.
4. Holes: an awl through printed guide holes, or a printed guide plate.
5. Paste through the stencil with a squeegee (Sn42Bi58), or conductive epoxy (no heat).
6. Pick-and-place: the arm drops parts into the funnel pockets. Tray pick-up points are at fixed poses.
7. Soldering / curing: conductive epoxy (no robot precision needed), or hand soldering / Pinecil. Stretch: the arm holds the iron through a printed guide.
8. Test: the arm presses the board onto the bed-of-nails fixture, and an ESP32 checks each connection against the KiCad netlist.

### Ranked by feasibility (most to least), with fallbacks
1. KiCad → board model, press piece, stencil, part nests, test fixture, plus printability checks
2. Print (venue printers or pre-printed)
3. Bed-of-nails connection check (fallback: multimeter)
4. Arm presses the press piece (fallback: hand press)
5. Arm rolls the tape (fallback: hand roller)
6. Arm sands (fallback: hand sanding)
7. Arm pick-and-place into funnel pockets (fallback: by hand)
8. Squeegee paste or epoxy (fallback: by hand)
9. Arm peels the backing and lays tape (fallback: human)
10. Soldering with the arm (fallback: epoxy or by hand)
11. Through-hole insertion (fallback: by hand)

### Optional gantry for precision work (cut, place, probe)
- A cheap used Marlin printer (Ender 3 class), controlled over USB serial G-code; it also works with OpenPnP. Or a venue printer lent as a robot, if the organizers allow it.
- It would bring back the earlier "tool mount on the printer" plan: servo-lift carriage with snap-in inserts for knife, roller, probe, vacuum, and a hot-nozzle soldering hack with a spare nozzle.

## SO-101 hardware
- Feetech **STS3215** servos: 6 for the follower, 12 with a leader arm. **MG90S servos are not compatible** (wrong size, too weak, no position feedback).
- Adapter: **Waveshare Bus Servo Adapter (A)** (jumper set to USB mode), or Feetech FE-URT-1.
  - The Waveshare "Serial Bus Servo Driver Board" (ESP32-based) only works with a USB passthrough mode, or a flashed 1 Mbps UART relay sketch.
- Power: 12V/5A for 12V follower servos, 5V/4A for 7.4V servos and the leader. Match the supply to the servo version.
- Print the follower (and leader) parts FIRST on the prep day.
- Also print: gripper tips (TPU pad), the tool rack, tool handles, a vacuum cup mount, and a base plate that clamps the arm and fixes the jig positions.

## Team split
- **User:** arm build, tools, jigs, physical process.
- **SW1:** KiCad parser → parametric jigs (board, press piece, stencil, part nests, test fixture), printability checks.
- **SW2:** LeRobot control, taught poses and demonstrations for press, roll, sand and pick-and-place; job runner; camera check.
- **SW3:** bed-of-nails netlist testing on the ESP32, dashboard (step status, pass/fail map, cost and lead-time timer), pitch.

## Electronics notes
- MG90S servos (if used for a gantry or grippers) connect straight to ESP32 pins, powered from a separate 5V ≥ 2A buck converter with a common ground; PCA9685 if many.
- 12V pump and valve: logic-level MOSFET modules (AO3400 / IRLZ44N / IRLB8721, **not IRF520**) plus flyback diodes (1N4007 / SS34).
- Pogo probes: ESP32 inputs with pull-ups and 1 kΩ series resistors. A bed of nails needs many inputs, so use a multiplexer (CD74HC4067) or I/O expander.

## Order list (final, by importance)
- **Tier 1:**
  - STS3215 ×6–12
  - Waveshare Bus Servo Adapter (A) ×1–2
  - 12V/5A and 5V/4A supplies
  - copper tape with conductive adhesive (25–50 mm wide; 0.05 and 0.1 mm)
  - PETG and TPU filament
  - P75 pogo pins ×40 with sockets
  - ESP32 ×2, CD74HC4067 multiplexers
  - sandpaper and a sanding sponge
  - a few bearings and springs (roller tool)
  - 1206 LEDs/resistors, 555 ICs, headers
  - multimeter, jumper wires
- **Tier 2:**
  - conductive silver epoxy
  - Sn42Bi58 paste and flux
  - 12V vacuum pump and valve, suction cups, tubing, luer needle tips
  - logic-level MOSFET modules and flyback diodes, buck converters
  - Pinecil
- **Tier 3:** USB camera, awl, squeegee, Kapton tape, scalpel (manual fallback), ATtiny85.

### Cancelled (they belonged to the old "P1S as robot" plan)
- spare P1S hotend
- drag-knife holder and blades
- 6×3 mm magnets and 6 mm steel balls
- MG90S ×4

**Exception:** keep the knife, magnets and MG90S servos only if the optional gantry (used Ender 3 or a lent venue printer) is likely.

## Prep-day print plan (P1S, 2026-09-18)
1. SO-101 follower parts (plus leader if you have its servos) — largest print, start first.
2. Tape test pieces (recessed traces; widths, gaps and depths varied), with press pieces.
3. Hole test piece.
4. Base plate with jig positions, arm clamp, tool rack, tool handles (roller, press pusher, sanding block, squeegee), TPU gripper tips, vacuum cup mount.
5. Demo board kits ×4–6 (board, press piece, stencil, part nest, test fixture), so the venue printers are optional.
6. Electronics box, cable guides.

## Prep-day tests, in order
1. Servos respond through the adapter (LeRobot port finding, reading positions).
2. Press-and-sand test on the tape test pieces (confirm the traces are isolated).
3. Arm assembly and calibration; teleoperated press and sand.
4. Epoxy or low-temperature solder on tape over PETG.

## 48-hour timeline
- **0–8 h:** SW1 generates jigs from a real KiCad file; SW2 teaches poses for press and sand; SW3 gets the fixture test working.
- **8–20 h:** end to end with press, sand and test.
- **20–32 h:** pick-and-place and paste or epoxy.
- **32–40 h:** stretch steps (tape laying, soldering). Stop adding features at hour 40.
- **40–48 h:** polish, backup video, pitch.
