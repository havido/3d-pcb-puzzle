# The KiCad → printable-parts pipeline

How `tools/kicad2fab.py` works today, what in it is specific to the goose/badge demo, and a roadmap for folding it into the general **KiCad PCB → STL** tool, `tools/kicad2cad` (branch `feat/kicad2cad`, plan in [kicad2cad-plan.md](kicad2cad-plan.md)).

## 1. Data flow

```
.kicad_pcb ──parse_sexpr──► nested lists
                               │
             extract()         │ copper_by_net()
   plate outline + cut-outs ◄──┴──► F.Cu / B.Cu shapely polygons per net, via positions
                               │
                 2D offsetting (shapely buffer / difference)
   cu → moat → rim → groove → teeth → plate_top → cutter_face ; tray, posts, clip, ...
                               │
                 Ops list:  {name, body, add|cut, z0, z1, polygons, circles}
                               │
              FeatureScript TEMPLATE  ──► *.fs ──► Onshape ──► STL / 3MF
```

Everything is **2.5D**: every feature is a 2D region extruded between two Z heights. All the design intelligence is in the 2D step; the FeatureScript only sketches, extrudes and booleans.

### The `Ops` list is the intermediate representation

`Ops.add(name, body, op, z0, z1, geom, circles)` records one prism. Per body, all `add` prisms are unioned, then `cut` prisms are subtracted in order. This list is backend-neutral — it maps one-to-one onto kicad2cad's "extrude these polygons from z0 to z1, then union" build step (see roadmap §4.1).

## 2. Board and cutter geometry

All values are fields of `P` at the top of `kicad2fab.py`. Cross-section through one trace (not to scale):

```
 z_face+CUTTER_T ┌───────────────────────────────────────────┐
                 │                 cutter                    │
        z_groove │        ┌───────────────────┐              │
                 │        │      groove       │              │
          z_face └──┐  ┌──┘                   └──┐  ┌────────┘
                    │  │ tooth                   │  │
   T+TRACE_H        │  │    ┌─────────────┐      │  │
   T+RIM_H     ┌──┐ │  │    │    trace    │      │  │ ┌──┐
   T        ───┘  │ └──┘    │             │      └──┘ │  └───
   T-MOAT_D       └─────────┘             └───────────┘
                rim   moat                      moat   rim
```

| 2D region | Construction | Notes |
|---|---|---|
| `cu` | union of F.Cu tracks + via pads, clipped 0.8 mm inside the plate | the raised lands |
| `moat` | `cu.buffer(MOAT_W) - cu` | 1.5 wide, 0.6 deep |
| `rim` | next `RIM_W` ring outside the moat | 0.8 wide, 0.4 tall; the anvil the tape shears against |
| `groove` | `cu.buffer(TAPE_T + SIDE_CL)` | cutter clearance around a taped trace (3 mm trace → 3.4 mm groove) |
| `teeth` | `(cu + moat).buffer(-SHEAR_CL) - groove` | 1.2 wide; `SHEAR_CL` = 0.10 is the number to tune |
| `back_tracks` | B.Cu tracks grown by `BACK_RECESS_CL` | 0.4 deep recess in the back |

Helpers that exist because CAD booleans are fragile:

- `solidify()` — open/close by 0.06 mm to remove point contacts, zero-width necks and hairline gaps.
- `clean()` — drops slivers under 0.3 mm².
- `STEP` (0.03) — faces that would be flush are deliberately offset. `EPS` (0.05) — stacked prisms overlap so unions are volumes, never face contacts.
- `Ops.add` warns if two regions of one op touch or a polygon is invalid.

**Shared moats.** When two different nets are closer than `2 × (MOAT_W + RIM_W)` = 4.6 mm, their moats merge, there is no rim between them and the tape is *not* sheared there. The generator reports each spot ("share a moat near (x, y)") and the builder scores the moat floor with a knife. This is the limitation behind roadmap item §4.2.

**Automatic placement.** Cutter alignment pins (`farthest_points`: three well-spread points clear of copper), pry scoops (two edge points far from copper), lock posts (`place_posts`: farthest pair in the free area over the tray walls), edge clip (`place_clip`: straight copper-free edge over a tray wall, minimising lift at the pogo pins).

## 3. What is hard-wired to the goose / badge

These are the things to parameterise before another board can go through:

| Where | Hard-coded | Should become |
|---|---|---|
| `kicad2fs.BADGE_CENTRE` | rotation centre (103.4, 103.6) | derived from the host board's bounds, or config |
| `kicad2fab.PINS_PORTRAIT` + `make_goose_template.PINS` | four pogo positions on the badge D-pad (duplicated in two files) | a list in a per-host config; or mark pogo vias in KiCad (net class / via size / a User layer) |
| `main()` switch scan | footprints named `SWn` with `SW-SMD` in the library id; 6×6×5 tact switches | config: "obstacles under the board" with height + footprint filter |
| `build_tray()` | badge slides in from its top end; `TRAY_START_Y`, `LOCATOR_Y`, `SPRING_Y` in badge coordinates; clamshell needs two holes in the badge | tray as an optional module with its own config |
| `--badge` is required | even for a board that docks to nothing | optional: no `--badge` → board + cutter only |
| `copper_by_net()` | reads `segment` and `via` only | also arcs, zones, filled polygons, footprint pads (the code exists in `kicad2fs.extract`, but without net names) |
| groove report line | assumes 3 mm traces | measure from the file |

## 4. Roadmap: generalising the pipeline

**Two generators exist. Do not grow both.**

| | `tools/kicad2fab.py` (Adit, this doc) | `tools/kicad2cad` (havido, branch `feat/kicad2cad`) |
|---|---|---|
| Reads | tracks + vias only, by net | every copper primitive (tracks, arcs, pads, vias, zones, graphics) with net + footprint ref, in a typed `Board2D` model |
| Builds | board with moat + shear rim, **cutter**, badge tray, keys, clip, plungers, pin gauge | plain board with raised copper, alignment holes, user-layer recesses / pockets |
| Output | Onshape FeatureScript | watertight STL + 3MF, preview, 1:1 PDF, SVG layers, `report.json` |
| Params | `P` namespace in the file | `params/3dpcb.yaml` recipe, validated |
| Tests | none (outputs are byte-reproducible) | pytest + GitHub Actions |

So the general tool is **kicad2cad**, and the fabrication know-how is in **kicad2fab**. The roadmap is mostly "port the second into the first". Rough order of value:

### 4.1 Port the shear-cutter geometry into kicad2cad (tickets #29 cutter, #15 generator)
Section 2 above is the spec. As recipe options on top of `Board2D`: `moat {width, depth}`, `rim {width, height}`, `cutter {side_cl, top_cl, shear_cl, tooth_floor_cl, thickness}`, then a second body, `cutter.stl`. Carry over `solidify()` / `clean()` and the `STEP` / `EPS` offsets — manifold booleans are more forgiving than Onshape's, but zero-width necks still make unprintable slivers.

The defaults differ today (kicad2cad: base 2.0, copper 0.6, 3 mm alignment holes; kicad2fab: plate 4.0, trace 1.0, 5.0 pins in 5.2 sockets). Agree on one set in `params/3dpcb.yaml` and record why (the 4.0 plate is for stiffness over the pogo pins; 1.0 trace height gives the tooth a sidewall to wipe the tape down).

Acceptance (kicad2cad plan, H-D): goose v3 through kicad2cad matches the kicad2fab board within 0.2 mm, or every difference is explained. `goose/goose_landscape_v3.kicad_pcb` and the generated `.fs` files are in the repo for that comparison.

### 4.2 Trace-spacing fixer (Adit's idea; fits ticket #31 design checks)
Different-net copper closer than ~5 mm (exactly `2 × (MOAT_W + RIM_W)` = 4.6 mm) shares a moat and needs a manual knife score. Options, cheapest first:
1. **Report** it like a DRC, with coordinates and the gap needed. kicad2fab already prints "share a moat near (x, y)"; move that into `report.json` and circle it in `preview.png`. Add a KiCad custom-rule snippet (`(rule ... (constraint clearance (min 4.6mm)))`) so KiCad's own DRC flags it while drawing.
2. **Adaptive moat**: where the gap is between ~3 and 4.6 mm, locally narrow the rim/moat, or put a single thin **centre ridge** in the shared moat with a split tooth either side, so the tape still shears.
3. **Push apart**: move track segments along their normals until the gap is met (iterative relaxation on the segment graph; endpoints on vias/pads stay fixed; keep 45° angles; re-check the outline margin). Write the result as a *new* `.kicad_pcb` for review in KiCad — never change geometry silently.
4. If a gap cannot be opened (pinned by pads), fall back to option 2 and say so.

### 4.3 Docking module (badge tray) as an optional add-on
Port `build_tray`, `place_posts`, `place_clip`, the relief pockets, plungers and pin gauge as a separate module that takes a *host* description: pogo positions, obstacle footprints + heights, rotation, tray style and extents (e.g. `hosts/htn2026_badge.yaml`). Section 3 lists what is hard-wired today. Boards that dock to nothing skip it.

### 4.4 Components on the board
kicad2cad already reads pads. Decide what they become: through-hole pad = land + lead-sized hole (min 1 mm); SMD pad = land; keep-clear around holes for the iron. Needed before any board with real parts.

### 4.5 Design checks before generating (#31)
Min trace width, min gap, min hole, copper-to-edge margin, isolated slivers, plate bigger than the bed (180 mm on the A1 mini → offer dovetailed tiles), no room for pins/posts. Fail with coordinates; optionally write markers onto `Cmts.User` in a copy of the board.

### 4.6 Coupon generator (#10)
A small board sweeping trace width, gap and `shear_cl` (one row per value), with embossed labels. Measured results replace the defaults in `params/3dpcb.yaml` and the guesses in CLAUDE.md.

### 4.7 Auto-widen thin tracks
Normal KiCad boards have 0.25 mm tracks. `min_track_width: 2.0` in the recipe: widen where neighbours allow, report where they don't.

### 4.8 Tests
Add goose v3 as a second fixture next to the synthetic test board. Property checks on the 2D step: teeth never intersect the groove, rim never intersects moat, every hole inside the plate, no two regions of one op touching. Until kicad2fab is retired, a golden-file test on its `.fs` output is cheap (it is byte-reproducible).

### 4.9 Nice to have
- Two-sided boards: a second cutter for the back copper instead of plain recesses.
- A printed knife-scoring guide for shared moats; estimate of tape area.
- Net labels embossed next to traces; component outlines from `F.Fab` as shallow locating pockets.
- A tiny web UI: upload `.kicad_pcb` → preview → download STL zip.
- Keep a CAD export (FeatureScript or STEP) for people who want to finish by hand; verify the current FeatureScript in Onshape.
