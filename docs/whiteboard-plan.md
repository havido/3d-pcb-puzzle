# "Canva for copper": the Design tab

A second tab in the existing web app where you **draw a board, or ask for one in words, then edit it and print it**. The current Convert tab is untouched; the Design tab hands its result to the same conversion pipeline.

Why this is tractable here and not in general: our boards have **no components, one copper layer and fat traces**. A design is *shapes plus a net name*. So the editor is a shape editor with fabrication rules baked in, not a PCB CAD program.

## 1. What's on screen

```
┌ Convert │ Design ─────────────────────────────────────────────────────────┐
│ tools    ╎                     canvas (1 mm grid)          ╎ inspector     │
│ ▸ select ╎        ┌───────────────────────────────┐        ╎ width  3.0 mm │
│ ▸ trace  ╎        │   ╭──────────╮                │        ╎ net    GOAL_1 │
│ ▸ hole   ╎        │   │  goose   │   ●pogo        │        ╎ points 7      │
│ ▸ outline╎        │   ╰──────────╯                │        ╎               │
│          ╎        └───────────────────────────────┘        ╎ RULES         │
│ nets     ╎                                                 ╎ ⚠ 2 nets 3 mm │
│ ● PENALTY╎                                                 ╎   apart       │
│ ● GOAL_1 ╎                                                 ╎ ✓ widths ok   │
│ ● GOAL_2 ╎                                                 ╎               │
│ ● GND    ╎                                                 ╎ [Convert → 3D]│
│          ╎                                                 ╎               │
│ templates╎                                                 ╎               │
├──────────┴─────────────────────────────────────────────────┴───────────────┤
│ 💬  "add a loop around the tail and connect it to pin 2"        [send] 🎙  │
│     ↳ applied: 1 outline, 2 traces        [accept] [undo]                  │
└────────────────────────────────────────────────────────────────────────────┘
```

**Only four kinds of object exist:**

| Object | What it is | How you edit it |
|---|---|---|
| **Outline** | one closed shape = the plate | drag vertices; presets: rectangle, rounded rectangle, circle, goose |
| **Trace** | polyline with a width and a net = a copper wall | click to draw, drag a vertex, click a segment to add one, backspace to delete; width and net in the inspector |
| **Hole** | circle with a diameter | drag it; "pogo" holes snap to the badge's fixed pin positions |
| **Label** *(stretch)* | text on the silk layer | — |

**Rules are live, not a later check.** Snap to a 1 mm grid, segments snap to 45°, and these are re-checked on every edit, drawn as a red halo on the offending shape and listed in the panel:

| Rule | Default | Why |
|---|---|---|
| trace width | ≥ 3 mm | the tape shears cleanly at this width |
| gap between different nets | ≥ 4.6 mm | closer and the two moats merge, so the tape isn't cut and someone has to score it by hand |
| copper to board edge | ≥ 4 mm | room for the moat and rim |
| hole diameter | ≥ 1 mm | printable |
| board size | ≤ 180 mm | the printer bed |

These are the numbers already in `CLAUDE.md` and `docs/PIPELINE.md`; they come from the recipe, not from hard-coded values.

## 2. What the AI does

The prompt bar is not a picture generator. **The model calls the same operations the toolbar exposes**, so anything it does is an ordinary edit: it lands in the undo stack, and you can drag its vertices afterwards. That is what makes "fully editable" true rather than a claim.

Tools the model may call:

| Tool | Arguments |
|---|---|
| `set_outline` | preset name + size, or explicit points |
| `add_trace` | points, net, width |
| `apply_template` | `loop`, `comb`, `spiral`, `zigzag`, `corridor`, with parameters |
| `route` | from object/point → to object/point, net (**deterministic A\* on the grid**, not the model's geometry) |
| `move_vertex`, `set_net`, `set_width`, `add_hole`, `delete` | object id + value |

Three guardrails:
1. **The model never emits raw coordinates for anything complex.** It picks a template and parameters, or calls `route`, which is our own pathfinder honouring the clearance rules.
2. **Every op is validated before it applies** (on-grid, inside the outline, legal net). An invalid op comes back to the model with the reason, and it gets one retry.
3. **Every AI turn is one undoable group,** shown as "applied: 2 traces, 1 hole" with Accept and Undo.

Example turns that must work for the demo:
- "make a goose-shaped board 150 by 130"
- "add a loop around the tail on GOAL_1"
- "connect that loop to pogo pin 2"
- "the two body traces are too close, push them apart"
- "make the maze harder"

## 3. How it reaches a printed board

The canvas document is written to a real `.kicad_pcb`, then handed to the existing pipeline:

```
canvas doc ──► .kicad_pcb ──► POST /api/boards ──► /api/convert ──► STL/3MF
   ▲                                                      │
   └────────── import an existing board (goose v3) ◄──────┘
```

Both directions matter. Export means KiCad users can carry on in KiCad, and it reuses everything already tested. Import means the Design tab can open **the real goose board** and edit it, which is the strongest thing to show a judge.

Document format (also the AI's schema, and what the URL/localStorage stores):

```json
{"version": 1, "units": "mm", "grid": 1.0,
 "outline": {"points": [[0,0], [150,0], [150,130], [0,130]]},
 "nets": [{"name": "PENALTY", "color": "#d9822b"}],
 "objects": [
   {"id": "t1", "kind": "trace", "net": "PENALTY", "width": 3.0, "points": [[10,10],[60,10],[60,40]]},
   {"id": "h1", "kind": "hole", "d": 1.18, "at": [30,20], "role": "pogo", "net": "GND"}]}
```

## 4. Build order

Each phase leaves something demoable. Times assume one person who already knows the repo.

| Phase | What | Time | Demoable after it |
|---|---|---|---|
| **P0** | Tab shell: `Convert | Design`, empty canvas, grid, outline preset, document store | 30 min | — |
| **P1** | Manual editing: draw a trace, select, drag vertices, delete, set net and width, undo/redo, 1 mm + 45° snapping | 1.5 h | "I drew a board" |
| **P2** | Export to `.kicad_pcb` → existing convert → jump to the Convert tab with the 3D result | 45 min | **draw → print**, the whole loop |
| **P3** | Live rules with red overlay and a list | 45 min | "it stops you making something unmakeable" |
| **P4** | AI prompt bar: `/api/design/chat` → tool calls → ops applied through the same reducer, with Accept/Undo | 1.5 h | **say it → edit it → print it** |
| **P5** | Import an existing board (goose v3) into the canvas | 30 min | "here's our real board, now change it" |
| Stretch | filled zones, SVG import, speech input (browser API, ~20 min), multi-select | — | — |

**Cut lines:** P0–P2 alone is a complete story. P4 is the sponsor track. P5 is the flourish. Stop wherever the clock says.

## 5. Where the code goes

```
web/app/src/design/          the new tab; nothing here imports from the Convert tab
  DesignTab.jsx              layout, tool state
  Canvas.jsx                 SVG canvas: grid, outline, traces, holes, handles
  doc.js                     the document, the ops, the reducer, undo/redo  ← the core
  rules.js                   the live checks (mirrors the server's checks)
  ai.js                      calls /api/design/chat, applies returned ops
web/api/design.py            doc schema, op validation, .kicad_pcb writer, A* router, /api/design/*
tests/test_design.py         writer round-trip, op validation, router, rules
```

New endpoints:

| Route | Does |
|---|---|
| `POST /api/design/kicad` | document → `.kicad_pcb` → returns a `board_id` the Convert tab can use |
| `POST /api/design/import` | `board_id` → document (tracks, outline, holes as editable objects) |
| `POST /api/design/chat` | document + prompt → validated ops (OpenAI key stays server-side) |
| `POST /api/design/route` | two points + net → a path that respects the clearances |

**The single most important test:** write a document to `.kicad_pcb`, parse it back with `kicad2cad`, and check the geometry matches. That keeps the new tab honest about producing real, convertible boards.

## 6. Risks

| Risk | What to do |
|---|---|
| The model invents unusable geometry | it only gets templates + `route`; every op is validated; one retry with the error |
| Scope creeps into a PCB editor | four object types, one layer, no components. Say no to footprints |
| The new tab breaks the working one | separate folder and state; the Convert tab imports nothing from `design/`; CI builds both |
| Venue wifi dies mid-demo | cache one full conversation and its result; be able to run the demo offline and say so |
| Time | phases are ordered so stopping early still demos |
