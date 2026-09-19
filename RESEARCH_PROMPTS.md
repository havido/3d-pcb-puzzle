# 3DPCB — Online Research Prompts

Paste the **shared preamble** first, then one prompt, into a deep-research tool (Claude Research, ChatGPT Deep Research, Perplexity, etc.). Each prompt is self-contained and names an owner. Results should be dropped into `research/<id>.md` so everyone can read them.

**Urgency key:** 🔴 tonight, before the prep day (2026-09-18) · 🟠 before the hackathon starts · 🟡 only if the branch it supports is chosen

---

## Updates after Q&A (2026-09-17) — append these lines to the named prompts

- **All prompts:** venue printers are **Bambu A1** (first come, first served; own filament / custom G-code / clip-on tools unconfirmed). Home printer is a P1S with a 0.4 mm nozzle, PETG and PLA only. No used Ender 3. Joining is by **soldering iron (adjustable 180–520 °C) only — no epoxy, no hot air**. We want to **avoid dry sanding dust**.
- **R1 add:** "Rank dust-free ways to isolate the foil over ridges: wet sanding with a rigid block, abrasive rubber/ink-eraser blocks, fibreglass pen, razor/card-scraper planing on guide rails, and sharp knife-edge ridges that shear the foil during pressing so no removal is needed. Which have been shown to work on 35–50 µm copper tape?"
- **R3 add:** "Focus on Bambu A1: slicing for it headlessly (Bambu Studio / OrcaSlicer CLI), getting a sliced .3mf/.gcode onto it via SD card vs LAN vs cloud when we don't own the printer, and realistic minutes for a 45×60×1.2 mm PETG plate."
- **R4 add:** "Are Waveshare ST3215 servos (12 V, 30 kg·cm) a drop-in substitute for Feetech STS3215 in LeRobot's SO-101 config? Which single-box SO-101 servo kits (servos + driver board + PSU) exist and who ships them fastest?"
- **R6 replace scope:** drop options (b) epoxy and hot-air/hot-plate reflow. Keep: iron-only technique with Sn42Bi58 paste or low-temp solder wire on copper tape over PETG/PLA (tip temperature, dwell time, flux, pre-tinning, Kapton under pads), and (c) solderless clamped contacts.
- **R8 add:** "Pins in hand are P75-B1 (conical, 1.02 mm body), no receptacles. How to mount them directly: perfboard hole fit, printed plate hole size, soldering wires to the tails."
- **R9:** reduce to the Bambu A1 clip-on/pen-plotter question only; skip used-Ender sourcing and OpenPnP.

---

## Shared preamble (paste before every prompt)

> Context: we are a 4-person team (1 mechatronics, 3 software) building a 48-hour hackathon project. Pipeline: KiCad file → FDM-printed PETG board whose traces are shallow recessed channels separated by thin raised ridges → one sheet of copper-foil tape is rolled/pressed into the relief → the ridge tops are sanded so the copper separates into isolated traces → solder paste or conductive epoxy → SMD parts (1206, SOIC / 2.54 mm pitch) placed through printed funnel "nests" by a low-precision SO-101 robot arm (LeRobot, Feetech STS3215 servos) → the bare board is netlist-checked on a pogo-pin fixture driven by an ESP32. Constraints: hobbyist budget, 0.4 mm-nozzle FDM printers only, open-source tools preferred, software teammates have no hardware experience.
> Rules for your answer: prefer primary sources (repos, official docs, forum/blog posts that include measurements) from 2024–2026; link everything; say explicitly what you could not verify; give concrete numbers (dimensions, temperatures, forces, times, prices) rather than adjectives; finish with a short "what I would do with 48 hours" recommendation and a list of the top 3 ways this will fail.

---

## R1 🔴 Copper-tape-on-printed-board process: prior art and parameters — owner: mechatronics

> Find and summarise every documented build of 3D-printed circuit boards that use copper foil tape, especially: "PCB Forge" by castpixel (Hackaday, ~Feb 2026), QWZ Labs' KiCad→STEP→Fusion raised-trace method (~Jan 2026), and Raccoon Lab's 2 mm raised-trace method (~May 2026). For each: is the tool/source open (repo link, licence)? Exact geometry used — channel depth and width, ridge height/width and wall angle, minimum trace and gap achieved, hole sizes; foil thickness and temper; adhesive type; how the foil was pressed (matched die vs soft pad vs roller; material and hardness); how copper was removed (grit, block type, wet/dry, strokes/time); print settings that mattered (layer height, top-surface pattern, ironing, Arachne, which face carries the traces); failure modes reported by the authors and in the Hackaday comments.
> Also search for adjacent techniques that isolate foil by abrasion or scraping over a relief (embossed-foil circuits, "sand-to-isolate", card-scraper/razor planing, hot-foil stamping for circuits) and any measurements of how much force and time abrasion of 35–50 µm copper foil takes.
> Deliver: a parameter table per source, a recommended starting test-coupon matrix (ridge height × ridge width × trace width × press method) for a 0.4 mm nozzle, and the known pitfalls.

## R2 🟠 KiCad → polygons → printable meshes toolchain — owner: SW1

> I need the fastest robust path, in Python, from a `.kicad_pcb` (KiCad 8/9/10) to watertight STL/3MF meshes for: (a) a board with recessed trace channels and raised isolation ridges, (b) a paste stencil, (c) a part-nest plate with funnel pockets per footprint. Compare these routes with working code snippets and known pitfalls: (1) `kicad-cli pcb export` (gerbers / svg / dxf / pos / ipc-d-356 / step — confirm exactly which subcommands exist in each KiCad version) + a Gerber parser (`gerbonara`, `pygerber`, `pcb-tools`) → `shapely`; (2) the `pcbnew` Python API directly (tracks, arcs, pad effective polygons, filled zones, Edge.Cuts → `SHAPE_POLY_SET` → shapely), including how to run it headless on Windows; (3) S-expression parsers (`kiutils`, `kicad-skip`, KiKit). Then compare 2D→3D options: `trimesh.creation.extrude_polygon`, `manifold3d`, `build123d`/CadQuery, OpenSCAD CLI — speed, robustness with hundreds of small polygons, and boolean reliability.
> Specifically cover: generating ridges as `buffer(copper, w) − copper` (the isolation-routing offset), guaranteeing minimum ridge width ≥ 2 extrusion lines, handling arcs/rounded pads/rotated footprints, the KiCad Y-axis flip and mirroring, net-per-polygon bookkeeping (needed later for testing), and existing open-source tools worth forking (`gerber_to_scad`, FlatCAM's isolation geometry, gerbolyze, PCB Forge if open).
> Deliver: a recommended stack, a ~100-line skeleton, and a list of DFM checks that are easy to compute with shapely (min trace, min gap, pad pitch, board ≤ tape width, single-sided/no-via check).

## R3 🟠 Headless slicing, printer dispatch, and fast thin-plate profiles — owner: SW1

> How do I slice STL/3MF from the command line and send the job to a printer with no GUI clicks, in 2026? Cover OrcaSlicer, PrusaSlicer and Bambu Studio CLIs (flags, profile handling, getting the time/filament estimate out as data). Cover dispatch: Bambu printers in LAN/Developer mode (MQTT + FTPS, libraries such as `bambulabs_api`, and the current state of Bambu's firmware authorisation restrictions), OctoPrint REST, Moonraker/Klipper, PrusaLink/PrusaConnect, and plain Marlin over USB serial (`printrun`/`printcore`).
> Then: what print settings give the fastest acceptable 40×60×1.2–1.6 mm PETG plate with fine top-surface relief (0.2–0.4 mm tall ridges, 0.45–0.9 mm wide)? Layer height, line width, top pattern, ironing yes/no, Arachne, speeds, whether to print the relief face up or against a smooth PEI sheet, and realistic minutes on a P1S/A1-class machine vs an Ender-3-class machine. Would a 0.2 mm nozzle be worth it?
> Deliver: copy-pasteable CLI commands, a dispatch code sketch per printer family, and a time table.

## R4 🔴 SO-101 + LeRobot: teach-and-replay without a leader arm, force limits — owner: SW2

> Using the current `lerobot` release (2026) and an SO-101 follower only (6× Feetech STS3215 on a Waveshare Bus Servo Adapter (A)): (1) exact install + motor-ID setup + calibration steps, and how well this works on Windows 11 natively vs WSL2 (usbipd) vs Linux/macOS; (2) how to disable torque, hand-guide the arm, and record joint-space waypoints, then replay them with smooth interpolation — using LeRobot's Feetech bus classes or `scservo_sdk`/`feetech-servo-sdk` directly — with example code; (3) whether `lerobot-record`/`lerobot-replay` can be used without a teleoperator device, or with a keyboard/gamepad teleoperator; (4) measured repeatability, absolute accuracy, payload and usable downward force of SO-100/SO-101 from people who measured it; (5) STS3215 registers for torque limit, P gain/compliance, overload protection time/threshold, temperature — and reports of overload/overheat trips under sustained load, with mitigations; (6) SO-101 print time and assembly time as reported by builders, and differences between the 7.4 V and 12 V servo versions and gear ratios for follower vs leader.
> Deliver: a bring-up checklist for tomorrow, a minimal waypoint teach/replay script, and the safe continuous-force envelope for pressing, rolling and sanding tasks.

## R5 🟡 Low-precision-arm pick-and-place: calibration, compliance, vacuum pickup — owner: SW2 + mechatronics

> For a ~1–2 mm-repeatable hobby arm placing 1206 parts and SOIC/2.54 mm-pitch ICs: (1) IK options for SO-101 (LeRobot kinematics/`placo`, `ikpy`, URDF sources) and how to correct poor absolute accuracy over a small 60×60 mm workspace — e.g. teaching 4–9 reference poses by touching a pin into printed holes and interpolating in joint space or fitting an affine/thin-plate correction; (2) passive-compliance tricks: funnel/chamfer lead-ins, floating or silicone-tube-coupled nozzles, remote-centre-compliance ideas printable on FDM; (3) cheapest reliable DIY vacuum pickup: 12 V micro diaphragm pump + 3-way solenoid vs modified aquarium pump, luer-lock blunt needles and silicone cups by part size, release tricks, and sensing pickup success cheaply; (4) simple part presentation for a demo (printed trays with oriented pockets vs cut tape strips in printed strip holders).
> Deliver: a recommended nozzle + tray + nest design with dimensions and tolerances for 1206 and a 2.54 mm-pitch 8-pin part.

## R6 🔴 Joining parts to copper tape on PETG/PLA/ASA without destroying the board — owner: mechatronics

> Compare, with numbers: (a) Sn42Bi58 paste (138 °C) reflowed by hot air, by a mini hot plate, or touched with an iron, on copper tape over PETG (Tg ≈ 80 °C), PLA, ASA/ABS and PC — what actually happens to the plastic and the tape adhesive, and which profiles people report working; (b) conductive silver epoxies and cheaper pastes (MG Chemicals 8331/8331D/8330, Atom Adhesives, generic silver paste syringes, nickel or carbon paints, "wire glue") — price per gram, per-joint cost, room-temperature and 60–70 °C cure times, joint resistance, shelf life, and availability with fast shipping; (c) solderless pressure contact — clamping SMD parts onto foil pads with a printed/TPU cover (elastomer-style contact): reported contact resistance and reliability; (d) tricks such as Kapton under the pads, thicker foil as a heat spreader, pre-tinning pads.
> Deliver: a ranked recommendation for a 30-minute, ~$1 board, with the per-board cost and time of each option.

## R7 🟡 Printed paste stencils and faster alternatives — owner: SW1 + mechatronics

> What is the smallest reliable aperture and web for an FDM-printed solder-paste stencil with a 0.4 mm nozzle (1206, 0805, SOIC-8 pads)? Thickness vs paste volume, print settings, first-layer tricks, and experiences with `gerber_to_scad` and similar tools. Compare with cutting stencils from Mylar/transparency/Kapton/cardstock on a Cricut/Silhouette vinyl cutter or a diode/CO2 laser (settings, minimum feature, minutes per stencil, open-source toolchains such as gerber→SVG→cutter), and with no stencil at all (syringe dots by hand or by a gantry).
> Deliver: recommendation per available venue tool, with dimensions.

## R8 🟠 Pogo-pin netlist tester on an ESP32 — owner: SW3

> Design a cheap bare-board continuity/isolation tester: (1) extracting nets and probe XY positions from KiCad — IPC-D-356 export (`kicad-cli` support by version) and Python parsers for it, vs reading pads/nets via `pcbnew`; (2) scan topologies for 16–48 points — CD74HC4067 drive/sense mux pairs vs MCP23017 I/O expanders (one pin driven low, all others input-pull-up) vs direct GPIO — with wiring, scan time, thresholds, and how to distinguish short/open/high-resistance; (3) a universal fixed-pitch (2.54 mm) pogo grid built on perfboard versus a per-board printed fixture — P75-series pin and R75 receptacle dimensions, hole sizes that work in FDM prints, pin travel and force (total force for 20–40 pins, relevant to a weak robot arm pressing the board down); (4) firmware/host options (Arduino vs MicroPython, serial JSON vs WebSocket) and any open-source bed-of-nails projects to fork; (5) an algorithm to choose a board XY offset on a fixed grid that maximises nets touched by exactly one pin and never straddles two nets.
> Deliver: schematic-level wiring description, firmware sketch, and host-side compare-to-netlist pseudocode that outputs a pass/fail map per net.

## R9 🟡 Cheap gantry as the precision robot — owner: mechatronics + SW2

> Cheapest way to get a G-code-controlled XYZ stage by this weekend: used Ender-3-class Marlin printers (what to check when buying, typical price), driving them over USB serial from Python (`printrun`/`printcore`, raw pyserial, homing, relative moves, M400 sync), OpenPnP on Marlin (setup time realistically), and **non-invasive clip-on tool mounts** for Ender 3 / Prusa MK3-MK4 / Bambu A1-P1 heads (pen-plotter mounts) that would let a borrowed venue printer act as a robot without modification. Cover tools: vacuum nozzle, syringe paste dispenser (stepper-extruder driven or pneumatic), spring-loaded probe for flying-probe testing, drag knife for foil (does drag-knife cutting of copper tape on a printed board actually work?), and the hot-nozzle "soldering" hack.
> Deliver: a go/no-go checklist, a bill of materials under ~$100, and a 6-hour bring-up plan.

## R10 🔴 Copper foil tape: what to buy and how to lay it flat — owner: mechatronics

> Compare copper foil tapes for embossing into a 0.2–0.5 mm relief: foil thickness (25/35/50/100 µm), temper (annealed vs rolled-hard), conductive vs non-conductive acrylic adhesive (does it matter when one un-seamed sheet covers the board?), widths available ≥ 50 mm and up to 100 mm or sheets, price per board, adhesive behaviour at 140–250 °C. Include EMI-shielding tape, slug/garden tape, stained-glass foil, and plain copper foil sheet + separate transfer adhesive (e.g. 3M 467MP/468MP) or spray adhesive. How do people apply wide foil without wrinkles (brayer hardness, squeegee, hinge method, application tape as used for vinyl)? Any label-dispenser-style peel-plate mechanisms that separate foil from liner automatically?
> Deliver: a buy list with same-week availability, and a recommended application method for a human and for a robot arm.

## R11 🟡 Pitch numbers: what does a prototype PCB cost and how long does it take today? — owner: SW3

> Give current (2026) cost and door-to-door lead time for a 50×50 mm 2-layer prototype board for a hobbyist in [OUR COUNTRY]: JLCPCB/PCBWay/local fabs including shipping and customs; home etching (toner transfer, photoresist) consumable cost and time; desktop mills (Bantam, Carvera, 3018-class) machine cost and per-board time; Voltera V-One/NOVA machine and ink cost per board; perfboard/breadboard. Also find numbers on how many hobbyists own a 3D printer vs a PCB mill, to support "use the machine you already own".
> Deliver: one comparison table (machine cost, per-board cost, lead time, minimum feature) we can put on a slide, with sources.
