# kicad2cad: implementation plan

Turn **any** KiCad board file (`.kicad_pcb`) into a 3D-printable 3DPCB board with one command. No GUI, no KiCad install needed.

- Ticket: #15, "Generator v1". Its outputs feed #29 (cutter plate), #31 (design checks) and #16 (on-screen goose map).
- Owner: havido (#15).
- **Status (Sat 10:00): phases 0–1 done on branch `feat/kicad2cad`, 42 tests passing.** Next: phase 2.
- Written 2026-09-19. The golden numbers below were measured from `Archive 2/badge.kicad_pcb`.

## 1. Goal, scope, definition of done

**Goal**
```
python -m kicad2cad <board>.kicad_pcb --recipe params/3dpcb.yaml -o out/<name>/
```
This produces a printable board (3MF + STL) with the copper **raised** on the top face (the positive half of the sandwich), plus previews and a report.

**In scope**
- The parser.
- The 2D model.
- The 3D build.
- Recipe options: extra layers, e.g. the goose's channels and seats.
- Alignment holes for the cutter.
- CLI, report, previews, tests, verification.

**Designed for, built elsewhere**
| Consumer | What it takes from here |
|---|---|
| #29 cutter plate (Akshat-Kalra) | the `Board2D` model + recipe |
| #31 design checks (Akshat-Kalra) | the `Board2D` model |
| #16 on-screen goose map (talfee) | the per-layer SVG export |

**Definition of done**
- [ ] One command produces `board.3mf`, `board.stl`, `preview.png`, `plot_1to1.pdf`, `layers/*.svg` and `report.json`.
- [ ] All automated tests pass locally and in GitHub Actions.
- [ ] The badge file converts, and every golden number in §5 matches.
- [ ] The test board is sliced (H-A), checked on paper (H-B), printed and measured (H-C), and matches the model within the tolerances in §7.
- [ ] Goose: the output from Adit's `goose.kicad_pcb` matches his hand CAD (#28) within 0.2 mm, or every difference is explained (H-D). *This waits on Adit committing his files.*
- [ ] `tools/kicad2cad/README.md` explains usage and the recipe. #15 is closed with evidence (photos + report).

## 2. How it works

```
.kicad_pcb ──parse──► Board2D ──shapes──► 2D polygons ──build──► 3D solids ──export──► 3MF / STL
 (S-expr)            (typed model,        (shapely,              (extrude +           + preview.png, plot_1to1.pdf,
                      KiCad coords)        per layer)             union, manifold)       layers/*.svg, report.json
```
- **Everything is 2.5D.** Every feature is a vertical extrusion between two heights. All the hard geometry (unions, holes, offsets) happens in 2D with `shapely`; 3D is only "extrude these polygons from z0 to z1, then union".
- **KiCad coordinates stay untouched inside `Board2D`** (mm, Y pointing down). The single Y flip (`y → −y`) happens in `build`. The cutter (#29) additionally mirrors, because it faces down.
- **Nothing is dropped silently.** Anything unsupported (text on copper, custom pads, trapezoid pads) becomes a warning in `report.json` and is printed on the terminal.

### Data model (the contract other tickets build on)
```python
@dataclass
class CopperFeature:
    kind: str            # "track" | "arc" | "pad" | "via" | "zone" | "graphic"
    layer: str           # "F.Cu" | "B.Cu"
    net: str | None
    ref: str | None      # footprint reference for pads, e.g. "SW2"
    geom: Polygon        # KiCad coords, mm

@dataclass
class Drill:
    x: float; y: float
    w: float; h: float   # w == h for round holes; oval otherwise
    angle: float         # degrees, KiCad convention
    plated: bool
    net: str | None

@dataclass
class Board2D:
    source: str                              # file path + sha256
    outline: Polygon                         # board shape; interior cut-outs are its holes
    copper: dict[str, list[CopperFeature]]   # per copper layer
    drills: list[Drill]
    user_layers: dict[str, MultiPolygon]     # e.g. "User.1" → goose channels
    warnings: list[str]
```

### Recipe (every tunable number lives here; `CLAUDE.md` rule)
```yaml
# params/3dpcb.yaml. Defaults until the coupon (#10) replaces them with measured values.
copper_layer: F.Cu          # this layer becomes raised copper; B.Cu is ignored, with a warning
base_thickness: 2.0         # mm, plastic under the copper
copper_raise: 0.6           # mm, raised copper height
min_drill: 1.0              # CLAUDE.md: holes ≥ 1 mm
small_drill: enlarge        # enlarge | skip | keep  (what to do with drills < min_drill)
arc_chord_mm: 0.02          # max chord error when turning arcs/circles into segments (0.1 would shrink a Ø6 hole by ~4 % in area)
include_zones: true
include_copper_graphics: true
alignment_holes:            # for the cutter plate's pins (#29)
  diameter: 3.0
  positions: auto           # auto = near 2 opposite outline corners, clear of copper; or [[x, y], ...]
extra_layers:               # goose-style extensions (docs/goose_spec.md, #12)
  User.1: {op: recess, depth: 1.5}
  User.2: {op: pocket, depth: 1.0}
```

### Repo layout
```
tools/kicad2cad/
  __main__.py      # CLI
  sexp.py          # tokenizer → nested lists
  geom.py          # footprint placement, arc/circle sampling
  model.py         # what the parser reads: tracks, pads, vias, zones, graphics, drills (KicadBoard)
  parse.py         # nested lists → KicadBoard (phase 1)
  summary.py       # counts for --summary / report.json
  shapes.py        # KicadBoard → Board2D polygons (phase 2)
  build.py         # Board2D + recipe → trimesh solids
  export.py        # 3MF, STL, preview.png, plot_1to1.pdf, layers/*.svg, report.json
  compare.py       # compare two meshes (goose check, §6 phase 5)
  README.md
params/3dpcb.yaml
tests/
  fixtures/make_testboard.py    # writes tests/fixtures/testboard.kicad_pcb (known geometry)
  conftest.py  test_sexp.py  test_geom.py  test_parse.py  test_testboard.py  test_badge.py  test_cli.py
  test_shapes.py  test_build.py   (phases 2–3)
.github/workflows/tests.yml     # pytest on every push
```

## 3. Test strategy (overview)

| Layer | What it proves | How |
|---|---|---|
| Unit | Each piece computes the right shape | Tiny inline S-expression strings; expected areas worked out by hand (e.g. track area = w·L + π(w/2)²) |
| Synthetic board | The whole pipeline, with exact answers | `make_testboard.py` generates a board whose features don't overlap, so expected areas and volumes are just sums |
| Real board (golden) | It works on a real, messy KiCad 9 file | The badge file: exact counts, coordinates and the pad↔track test in §5 |
| Mesh validity | Output is printable | `is_watertight`, `is_volume`, volume > 0, bounds = outline × height |
| Determinism | Same input → same output | Hash of the binary STL is identical across two runs |
| Slicer (manual) | Bambu Studio accepts it | H-A |
| Physical (manual) | Printed mm = model mm; no mirror or scale mistakes | H-B paper overlay, H-C calipers |
| Cross-check | Matches an independent model | H-D: Adit's hand CAD for the goose |

## 4. The test board (a synthetic fixture with known answers)

`tests/fixtures/make_testboard.py` writes `testboard.kicad_pcb` **and** `testboard.expected.json`. The expected file holds areas and volumes worked out with plain geometry formulas, not by running the pipeline, so the tests can't agree with themselves by accident. It's also the board we print in H-C. It's 50 × 40 mm at KiCad (100, 100), a ~20 min print, and no two copper features overlap.

| Feature | Why it's there |
|---|---|
| Outline: 50 × 40 rectangle with one R5 rounded corner (`gr_arc`) | outline made of lines + an arc |
| Interior cut-out: Ø6 circle | holes inside the outline |
| 4 straight tracks, 25 mm long, widths 1.0 / 1.5 / 2.0 / 3.0 mm | trace widths to measure with calipers (H-C) |
| One 90° arc track, R8, 2 mm wide | arcs (the badge has none) |
| One 45° track, 2 mm wide | non-axis-aligned tracks |
| Footprint `P1` **rotated 90°**: round pad Ø3 with 1.0 drill, rect 4 × 2, oval 4 × 2, roundrect 3 × 2 (ratio 0.25) | pad shapes + the rotation formula |
| Via: size 2.0, drill 1.0 | vias |
| Filled zone `GND`: 8 × 8 square | zones |
| Plain holes Ø1.0 / 1.5 / 2.0 | hole sizes to measure (H-C) |
| An "L"-shaped filled copper polygon (`gr_poly`) in the top-left corner | mirror check: the L must read the same way on paper, on screen and in plastic (H-B/H-C) |
| `gr_text "HONK"` on F.Cu | must produce exactly one warning |
| `User.1` rectangle 20 × 4 | recipe "recess" operation (goose channels) |

## 5. Golden numbers from the badge (`Archive 2/badge.kicad_pcb`, KiCad 9.0)

Measured during planning. `tests/test_badge.py` asserts them.

| Check | Expected |
|---|---|
| Outline bounding box (KiCad coords) | x 55.86 → 150.89, y 29.92 → 177.26 (≈ 95.0 × 147.3 mm), 243-point `gr_poly` |
| Interior holes | 4 × Ø4.45 at (74.58, 33.79), (132.28, 33.82), (74.59, 173.21), (132.29, 173.24) |
| F.Cu tracks / arcs | 634 segments, 0 arcs (arcs are covered by the test board) |
| Vias | 88 (60 × 0.8/0.4, 24 × 0.6/0.3, 4 × 1.2/0.6) |
| Pads touching F.Cu | 315 (300 `F.Cu F.Mask F.Paste` + 4 `F.Cu F.Mask` + 11 `*.Cu`) |
| Pad shapes (whole board) | rect 202, roundrect 197, oval 48+4, circle 5+7, **custom 1 → 1 warning** |
| Oval drills | 4 |
| Zones | F.Cu GND with 15 filled polygons; 2 keep-out areas with no net → ignored, not copper |
| Graphics on F.Cu | 2 `gr_circle` + 1 `gr_rect` → copper; **1 `gr_text` → 1 warning** |
| Pad positions (±0.01 mm) | SW2 pad 1 = (73.83, 118.93) GND · SW10 (180°) pad 1 = (116.54, 152.10) ESP32_BOOT · U8 (90°) pad 1 = (107.60, 138.09) SR_SHLD |
| **Pad ↔ track test** | ≥ 331 pads sit within 0.05 mm of a same-net track end (identical at 0.01 mm), ≥ 148 of them on 90°/270° footprints. The wrong rotation sign gives 185 / 2, so this test catches it. |

**Rotation rule (verified by the pad ↔ track test):** a pad's `(at x y angle)` gives its position in the footprint's own coordinates, before rotation. Its *angle* already includes the footprint's rotation.
- To place a pad: `gx = fx + x·cos r + y·sin r`, `gy = fy − x·sin r + y·cos r`, with `r` = the footprint's angle.
- To orient the pad's shape: rotate it by the pad's own angle, not by the footprint's angle again.

## 6. Build phases

Each phase ends with something you can run and check. Times are for one person new to the libraries.

### Phase 0: setup (20 min)
- [ ] Branch `feat/kicad2cad`.
- [ ] `python3 -m venv .venv && source .venv/bin/activate`
- [ ] `requirements.txt`: `shapely>=2 trimesh manifold3d mapbox_earcut pyyaml matplotlib pytest`
- [ ] Create the package skeleton from §2, with one placeholder test.
- [ ] `.github/workflows/tests.yml`: Python 3.12, install requirements, run `pytest -q`.

**Verify:** `pytest -q` → `1 passed`. Push the branch → the repo's **Actions** tab shows a green check.

### Phase 1: read the file (60–75 min): ✅ done
- [ ] `sexp.py`: tokenizer + nested-list builder. It must handle quoted strings with spaces and `\"`. Keep numbers as strings until you use them. Parses the 11 MB badge file in about 1 s.
- Built as an intermediate step: `parse.py` produces a `KicadBoard` (`model.py`) with every primitive already placed in board coordinates. Phase 2's `shapes.py` turns that into the `Board2D` contract above.
- [ ] `parse.py` → `Board2D`:
  - **Outline:** read `gr_line`, `gr_arc`, `gr_circle`, `gr_rect`, `gr_poly` on `Edge.Cuts`, plus `fp_*` shapes on `Edge.Cuts` inside footprints. Join them with `shapely.ops.polygonize`. The largest ring is the outline; rings inside it become its holes. If the outline isn't closed, fail with the coordinates of the gap.
  - **Copper:**
    - `segment` (start, end, width, layer, net)
    - `arc` (start, mid, end)
    - `via` (at, size, drill, layers)
    - footprints: `at` + rotation, then pads (type, shape, `at`, size, `roundrect_rratio`, drill incl. `oval`, layers incl. `*.Cu`, net)
    - `zone` → `filled_polygon` per layer; skip keep-outs
    - `gr_*` shapes on copper layers
  - **Drills:** from pads (plated or not) and vias.
  - **User layers:** `gr_poly`, `gr_rect`, `gr_circle` on `User.*`.
  - **Warnings:** text on copper, custom and trapezoid pads, zones with no fill (fall back to the zone outline), anything on B.Cu when `copper_layer` is F.Cu.
- [x] `python -m kicad2cad <file> --summary` prints the counts. The pad ↔ track test also runs in phase 1, since it only needs pad positions.

**Tests**
- `test_sexp.py`: nesting; quoted strings with spaces and escaped quotes; empty lists.
- `test_parse.py`:
  - the test board's counts match `expected.json`
  - an outline built from 4 lines + 1 arc closes
  - an outline with a gap fails with a clear message
- `test_badge.py`: every row of §5 except the pad ↔ track test (that comes in phase 2).

**Verify:** `python -m kicad2cad "Archive 2/badge.kicad_pcb" --summary` prints exactly the counts in §5.

### Phase 2: shapes → 2D (60–90 min)
- [ ] **Track:** `LineString([a, b]).buffer(w/2)`. Round ends match how KiCad draws tracks.
- [ ] **Arc:** find the circle through start/mid/end, sample it at `arc_chord_mm`, then buffer.
- [ ] **Pads:**
  - circle
  - rect
  - roundrect (corner radius = ratio × min(w, h))
  - oval (a stadium: `LineString` of length w − h, buffered by h/2)
  - trapezoid → treated as rect + warning
  - custom → drawn as its anchor shape + warning

  Place each pad with the rotation rule in §5.
- [ ] **Via:** a circle. **Zone:** its filled polygons. **Graphics:** buffer lines and arcs by their stroke width; add filled shapes.
- [ ] **Per copper layer:** `unary_union` (one call, not a loop) → subtract drills → clip to the outline.
- [ ] `preview.png`: top view. Outline in grey, copper in orange, drills in white, warnings marked with red circles. Scale bar and a "TOP VIEW (as in KiCad)" label.

**Tests**
- `test_shapes.py`:
  - track area = w·L + π(w/2)²
  - a pad rotated 90° swaps its bounding box
  - roundrect and oval areas match their formulas
  - arc end points hit start and end within 0.01 mm
- Test board: copper area matches `expected.json` within 0.5 %.
- Badge: the pad ↔ track test from §5.

**Verify:** open `out/badge/preview.png` next to the [iBOM](https://hackathon.github.io/badge-hardware/badge-ibom.html) (front side). The D-pad, the USB-C connector and the 4 corner holes must be in the same places, with nothing mirrored.

### Phase 3: 3D + export (45–60 min)
- [ ] Flip Y (`y → −y`) once, here.
- [ ] Solids:
  - `base = extrude(outline − drills, 0 → base_thickness)`
  - `copper = extrude(copper_2d − drills, base_thickness → base_thickness + copper_raise)`
  - union the two with manifold
- [ ] Export `board.3mf` + `board.stl` (binary, deterministic).
- [ ] `plot_1to1.pdf`: exact physical size (figure size = board size ÷ 25.4 inches; the drawing fills the page edge to edge). Include a **50 mm scale bar** and "print at 100 % / Actual size".
- [ ] `layers/<layer>.svg`: outline, copper and user layers, in mm (for #16).
- [ ] `report.json`:
  - input sha256
  - counts, bounding box, areas, volumes
  - warnings
  - timings
  - recipe used

**Tests**
- `test_build.py`:
  - `is_watertight` and `is_volume`
  - volume = outline area × base + copper area × raise (minus drills), within 0.5 %
  - bounds z = [0, base + raise]
  - xy bounds = outline bounding box with Y flipped
- `test_cli.py`:
  - the CLI on the test board creates all 6 outputs
  - two runs produce an identical STL hash
  - the badge run takes < 60 s

**Verify:** do **H-A** (slice) and **H-B** (paper overlay) below on the test board.

### Phase 4: recipe extras (45 min)
- [ ] `extra_layers` operations:
  - `recess` (lower the top surface by `depth`)
  - `pocket` (same, for small seat pockets)
  - `through` (cut all the way through)
- [ ] `alignment_holes`:
  - `auto`: place 2 holes near opposite outline corners, at least 3 mm from any copper and the edge
  - or explicit positions
- [ ] `small_drill` policy (enlarge / skip / keep), with a count in the report.

**Tests:**
- The User.1 recess removes exactly `area × depth` of volume.
- Alignment holes never touch copper.
- `small_drill: enlarge` turns a 0.3 mm via drill into 1.0 mm.

**Verify:** re-slice the test board (H-A). The channel is visible as a lower area in the layer preview.

### Phase 5: real inputs + comparison (30–45 min, once Adit's files are in #28)
- [ ] Run the tool on `kicad/goose.kicad_pcb`.
- [ ] `compare.py ours.stl adit.stl`:
  - move both to the origin
  - try the 8 orientations (4 rotations × mirrored or not) and keep the best top-view overlap
  - report size differences, top-view overlap (IoU), Hausdorff distance, and copper and channel depths from slices at several heights
- [ ] Set the recipe heights to match Adit's hand CAD (ask him: base thickness, copper height, channel depth), then compare again.

**Pass:** sizes within 0.2 mm, top-view IoU ≥ 0.98, Hausdorff ≤ 0.2 mm. Every remaining difference is written in the #15 comment with its reason.

### Phase 6: docs + handoff (20 min)
- [ ] `tools/kicad2cad/README.md`:
  - usage
  - every recipe key
  - supported and unsupported KiCad elements
  - how to read `report.json`
- [ ] Comment on #29 and #31 (Akshat-Kalra): "`Board2D` is ready; import it from `kicad2cad.parse`." Show the dataclass.
- [ ] A demo line for the pitch (#34): the CLI prints `KiCad → printable board in X.X s`.

## 7. Hardware steps you do by hand (explained like you're 5)

The code can check that the numbers add up. Only these steps can check that the **real object** is right. Each one says what it's for, exactly what to do, and how to tell whether it worked. If something looks wrong, take a photo and post it on #15 before doing anything else.

### H-A: "Will the printer accept it?" (slice in Bambu Studio, 10 min)
**What it's for:** a *slicer* turns our 3D shape into step-by-step printer instructions. If the slicer complains, the printer would fail too. Finding out here costs 2 minutes instead of a wasted print and a lost place in the printer queue.

**You need:** your laptop, the free [Bambu Studio](https://bambulab.com/en/download/studio), and `out/testboard/board.3mf`.

1. Install Bambu Studio and open it. When it asks which printer you have, pick **Bambu Lab A1**, nozzle **0.4 mm**. For filament pick **PETG** (ask whoever runs prints (#6) which PETG is loaded).
2. **File → Import → Import 3MF/STL…** and pick `board.3mf`. If it asks "load as a single object with multiple parts?", click **Yes**.
3. Look at the board on the grey plate. It should **lie flat, with the copper bumps pointing up**. If it's standing on an edge or floating in the air, stop: that's a bug in our file.
4. Use the print profile from `print/profiles/` (#6). If there isn't one yet, set **Layer height 0.20 mm** and leave everything else alone.
5. Click **Slice plate** (top right).
6. Check three things:
   - **Warnings:** a red or orange message at the bottom? Read it.
   - **Time:** "Total time" at the top right. The test board should take about 15–30 min.
   - **Layers:** drag the slider on the right side **from the top down**. The top 3 layers (0.6 mm) should show **only the trace and pad shapes**; below that, the whole board. The holes should be holes in every layer.

✅ **Right:** no red messages; the time is reasonable; the top layers show only copper shapes; the holes go all the way through.
❌ **Wrong:** "floating regions" or "empty layer" warnings, traces missing from the top layers, holes filled in, or a time over an hour → screenshot on #15.

### H-B: "Is it the right size, and not mirrored?" (paper check, 10 min, no 3D printer)
**What it's for:** the two classic mistakes when turning a circuit board into a 3D shape are **wrong size** (e.g. inches mixed up with millimetres) and a **mirror image** (the board flipped left-to-right). A mirrored board means every part would be soldered backwards. One sheet of paper catches both before we spend any printer time.

**You need:** a normal paper printer, a ruler, and `out/testboard/plot_1to1.pdf`.

1. Open the PDF and print it at **"Actual size" / "Scale 100 %"**, **not** "Fit to page". (macOS Preview: File → Print → Scale: 100 %.)
2. Measure the **50 mm scale bar** on the paper with the ruler.
3. Find the **L-shaped marker** in the top-left corner of the board. Compare it with `preview.png` on screen. It must point the same way.
4. Measure the board outline on paper. It should be 50 × 40 mm.

✅ **Right:** the scale bar is 49.5–50.5 mm, the outline is 50 × 40 mm, and the L points the same way on paper and on screen.
❌ **Wrong:**
- The scale bar isn't 50 mm → the print dialog shrank it; reprint at 100 %. Still wrong → it's our bug; post on #15.
- The L is reversed → **mirror bug**. Do not print; post on #15.

Keep the sheet. After H-C, lay the plastic board on top of it: the outlines and holes should line up.

### H-C: "Is a millimetre in the file a millimetre in plastic?" (print + measure, ~20 min print + 15 min)
**What it's for:** it proves our sizes come out right in real plastic, and shows how much the printer shrinks small holes and thin traces. Akshat-Kalra's design checks (#31) and the goose's dimensions depend on these numbers. It's also the first physical "KiCad file → board" for the pitch.

**You need:** the sliced file from H-A, a venue A1 (see `print/README.md` from #6, or ask whoever runs prints), **digital calipers** (borrow from Adit or the hardware desk), and your phone for photos.

1. In Bambu Studio: **Export plate sliced file** (a `.gcode.3mf`). Send it to the printer the way `print/README.md` says (SD card or network).
2. Start the print and **watch the first ~3 minutes.** The first layer should be flat and stuck to the plate. If the plastic curls up or gets dragged around like spaghetti, stop the print and ask Adit or the venue staff.
3. When it's finished, wait ~5 min for it to cool. Then gently bend the flexible build plate and the board pops off.
4. Log the print in `print/LOG.md`.
5. **Calipers, the basics:**
   - Press the button to turn them on. Close the jaws completely and press **ZERO**.
   - The **big lower jaws** measure outside sizes (length, width, trace width).
   - The **small upper jaws** go *inside* a hole and open outwards to measure its diameter.
   - The **thin rod** that slides out of the end measures depth and height.
6. Fill in this table and post it on #15:

| What | Model (mm) | Measured | OK if |
|---|---|---|---|
| Outline length | 50.00 | | ± 0.3 |
| Outline width | 40.00 | | ± 0.3 |
| Total height (board + copper) | 2.60 | | ± 0.15 |
| Copper step height (rod: top of a trace down to the board surface) | 0.60 | | ± 0.10 |
| Trace widths 1.0 / 1.5 / 2.0 / 3.0 | as named | | ± 0.15 each |
| Cut-out Ø6 | 6.00 | | ± 0.3 |
| Holes Ø1.0 / 1.5 / 2.0 | as named | | printed holes usually come out 0.1–0.3 mm small: **record, don't fail** |

7. Take photos: the top view with a ruler next to it, and a close-up of the L marker.

✅ **Right:** every "OK if" holds, and the L marker points the same way as in `preview.png`.
❌ **Wrong:**
- Everything is off by the same percentage → a size/unit bug in our file; post on #15.
- Only the holes are small → normal. Record how much; it becomes a correction in the recipe.
- A thin trace is missing or blobby → the printer can't do that width. Record the smallest width that printed cleanly; #31 uses it.

### H-D: "Do the code and Adit's hand-made model agree?" (goose check, 10 min, once Adit's files are in #28)
**What it's for:** Adit built goose v0 by hand; our tool builds it from the same KiCad file automatically. If two independent routes give the same object, we can trust the tool for goose v1 and any future board. If they don't, one of them has a bug, and we find it before v1 prints.

1. Ask Adit for his CAD model exported as **STL in millimetres**. Also ask for his three heights: base thickness, copper height, channel depth. Commit them to `cad/goose_v0/`.
2. Run the automated comparison (§6 phase 5). No hardware needed for that part.
3. Once Adit's v0 print exists: print our `goose/plot_1to1.pdf` at 100 % (as in H-B) and lay his printed goose on it.

✅ **Right:** the compare report passes, and on paper the outline and channels line up with his print to within about half a millimetre by eye.
❌ **Wrong:** post the report and a photo on #15 and tag Adit. Decide together whether his CAD or our tool is right.

### H-E (optional, with Adit): "Does a converted board work as a circuit?" (20 min)
**What it's for:** the final proof of the whole idea: our raised copper shapes become real, working wires once tape is applied.

1. With Adit: put copper tape over the test board's 4 straight traces and press it down firmly. Adit trims it along the trace edges with a hobby knife.
2. **Multimeter, the basics:** turn the dial to **Ω** or to the **continuity** symbol (looks like a sound wave; it beeps).
3. Touch one probe to each end of the **same** trace → it should **beep** or show **less than 1 Ω**. That means the wire works.
4. Touch the probes to **two neighbouring** traces → it must **not** beep and should show **OL** ("open"). That means they aren't shorted.

✅ **Right:** every trace is under 1 Ω end to end, and every neighbouring pair shows OL.
❌ **Wrong:** a short means leftover tape between traces (trim again). No reading means the tape is torn. Post it on #15; it feeds the coupon results (#10).

## 8. Timeline and cut lines (Saturday, revised 10:00)

| When | What |
|---|---|
| ✅ by 10:00 | Phases 0–1 (parser + 42 tests). |
| 10:00 → 11:30 | Phase 2 (shapes → 2D + `preview.png`), as far as it gets. |
| 11:30 | Workshop, then the badge app (your critical path to M2 at 21:00). |
| after | Phase 3, then H-A + H-B, then submit the test-board print (H-C). Phases 4–6 and H-D: you in gaps, or hand over to Akshat-Kalra (#29/#31 build on this anyway). Decide at 11:30 based on progress. |

**MVP cut line = phases 0–3 + H-A + H-B.** If only that is done, goose v1 can still be made from Adit's hand CAD (#28), and the pitch can show the tool converting the test board and the badge.

## 9. Risks and fallbacks

| Risk | Sign | Fallback |
|---|---|---|
| The badge conversion is slow | > 60 s | Union per net first, then everything; `simplify(0.01)` before extruding |
| `manifold3d` won't install | pip error | Export base and copper as separate bodies in one 3MF (the slicer merges overlapping bodies) |
| `extrude_polygon` fails | "earcut" or triangulation error | `pip install mapbox_earcut` (or `triangle`) |
| An older or unusual KiCad file | parse errors | Support KiCad 8/9 (file `version` ≥ 20240108; the badge is 20241229); warn on anything older |
| Too many unsupported elements (text, custom pads) | long warnings list | `kicad-cli pcb export gerbers` + `gerbonara` (needs a KiCad install), which also accepts boards from other design tools |
| Mirror or scale bug | H-B fails | Fix before any print; H-B exists to catch exactly this |
| Adit's files not in the repo | #28 still open | Phase 5 and H-D wait; the MVP doesn't depend on them |
