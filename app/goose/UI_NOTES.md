# UI notes for the Goose Doctor screens (@talfee)

Written 2026-09-19 for whoever works on `app/goose/ui.lua`. Read `app/CLAUDE.md`
first (platform limits + the game/ui contract), then this.

## The game changed: no organs, no seats

The hardware lead finished the real board (`goose/goose_landscape_v3.kicad_pcb`,
picture in `goose/goose_landscape_v3_check.png`), and it is a **steady-hand
maze**, not the Operation game:

- The plate is a flat goose. Its outline is drawn twice in copper (head/neck/back
  and breast/belly). Both are one electrical line: **PENALTY**.
- Two copper loops are the targets: **GOAL_1 = the tail loop**, **GOAL_2 = the
  belly loop**.
- The tweezers are wired to ground. Touching copper = that line is "pressed".

**Rules:** a countdown starts; every touch of the outline costs seconds (one
penalty per touch, repeats inside 0.5 s ignored); you win by touching **the tail
loop first, then the belly loop**; touching the belly loop early does nothing;
you lose when the clock hits zero. There is no organ to pick up or put down.

## What that means for the screens

| Screen | Wording now | Why |
|---|---|---|
| operating, stage 1 | "Reach the TAIL loop" (placeholder — your call) | replaces "Remove the organ" |
| operating, stage 2 | "Now the BELLY loop" (placeholder) | replaces "Deliver the new organ" |
| start / success / failure | say the start button + "HOME exits" | see buttons below |

- `info.stage` is `"goal1"` or `"goal2"` (it used to be `"remove"` / `"deliver"`).
- Stars are gone: no `set_stars`, no `info.stars`. A round is lost on time only.
- **Most badge buttons are physically covered by the plate.** Only two stick out
  through cut-outs: one to start (SW6 — we don't know yet whether the badge
  reports it as A, B or AUX1, so the game accepts all three) and HOME, which
  quits the app. So no "B Quit" on screen. Until SW6 is identified, wording like
  "Press the side button to start / HOME quits" is safest; if you prefer "A
  Start", keep it easy to change in one place.
- Everything else you designed still fits: start, operating with the big timer,
  success, failure.

## Getting your artwork onto the badge

The screen is **320x240**, and a whole app (code + every image) has to fit in a
**64 KiB storage budget** (`app/CLAUDE.md`'s "Platform" section, `APP_QUOTA` in
`badge.py`). That budget is the thing that decides how you can use your Canva
art -- read this before you export anything.

Your start screen already ran on a real badge as one full-screen 16-colour
image (38 KB): `demo_home_on_badge.png` in this folder is the screenshot taken
off the badge, handwritten text and all. So the art works -- the only question
is the budget below.

### The numbers (measured, not estimated)

`badge.py img` can write two different `.bin` formats. Both are LVGL v9
image files; which one you get is the `--colors` flag.

| Format | Bytes/px | 320x240 full screen | 120x120 sprite |
|---|---|---|---|
| RGB565A8 (default, no `--colors`) | 3 | **230,412 B** -- does not fit | ~43,212 B |
| I4 indexed, `--colors 16` | ~0.5 | **38,476 B** -- fits, proven on hardware 2026-09-19 | ~7,276 B |
| I2 indexed, `--colors 4` | ~0.25 | ~19,228 B | ~3,676 B |

Formulas if you want to size something before converting it (w, h in
pixels): `RGB565A8 = w*h*3 + 12`, `I4 = w*h/2 + 76`. (I2 and I1 follow the
same shape with 1/4 and 1/8 byte per pixel instead of 1/2; `badge.py img`
prints the real size either way, so you don't have to do the math.)

**The practical consequence: only one full-screen image fits in the budget
at all**, even at I4 -- and that's before any Lua code or other images. You
can't ship four different full-screen pieces of art for start / operating /
success / failure. Don't design them as four flat exported screens.

### The approach that actually fits: background box + small art pieces

Keep the background a solid `badge.ui.box` in code, using your exact Canva
colours (already in `ui.lua`: start/operating `0xfce884`, success `0xb9fc84`,
failure `0xff5757`). Export **only the actual artwork** from Canva as
tight-cropped, transparent PNGs, and lay them over the box as `badge.ui.image`
widgets:

- goose poses (idle, success, failure, whatever you draw)
- the "Goose Doctor" title/logo, if it's a wordmark rather than a font
- button-hint chips, icons, decorative bits

Crop each one tightly in Canva (export just the bounding box of the art, not
a 320x240 canvas with mostly empty space) -- a 120x120 sprite is ~43 KB as
RGB565A8 but only ~7 KB as I4 (see the table). Small, cropped, indexed pieces
are how several images fit in 64 KiB where one full-screen one doesn't. The
countdown timer stays a real `label` (as it is today) so `set_time` can keep
updating it -- never bake the timer into an image.

### Exact commands

```sh
# one image, indexed (use for anything that's most of the screen, or several
# images at once -- 16 colours is the format proven on hardware):
app/.venv/bin/python app/tools/badge.py img my_goose.png app/goose/img/goose_idle.bin --colors 16

# resize first if Canva exported it bigger than you need on screen:
app/.venv/bin/python app/tools/badge.py img my_goose.png app/goose/img/goose_idle.bin --size 120x120 --colors 16

# small icon/chip where RGB565A8 (the default, no --colors) is small enough anyway:
app/.venv/bin/python app/tools/badge.py img chip.png app/goose/img/chip.bin --size 56x56
```

Each run prints the output size, and warns if it's getting close to the
budget. `.bin` files belong in `app/goose/img/`; `build`/`push` pick up
anything already there as-is (`.png` files in that folder get auto-converted
to RGB565A8 instead, so for anything full-screen-sized, convert to a `.bin`
with `--colors` yourself rather than dropping the PNG in).

Reference the file from `ui.lua` by name, no path:

```lua
local goose = badge.ui.image(s, "goose_idle.bin")
```

Then build and push as usual:

```sh
for t in goose preview diag; do app/.venv/bin/python app/tools/badge.py build $t; done
app/.venv/bin/python app/tools/badge.py push preview
```

### Gotcha: the web IDE's image button is not for this

The badge web IDE's "Choose image" button crops and resizes whatever you give
it down to a **42x42 launcher icon** -- it's for the little icon that shows
up in the app grid, not for screen art. If your exported art comes back
tiny, blurry or cropped to a square after going through the IDE, that's why.
Always convert with `badge.py img` (above) and let `push` upload it as a
normal file instead.

### Worked example

```lua
-- background box in the screen colour, plus one image and a label on top
local s = screen(root, "start", YELLOW)          -- badge.ui.box(root, 320, 240)
local goose = badge.ui.image(s, "goose_idle.bin") -- app/goose/img/goose_idle.bin
goose:align("center", 0, -20)
local title = badge.ui.image(s, "title.bin")      -- your wordmark, cropped tight
title:align("top_mid", 0, 10)
buttons_hint(s, "Start")                          -- existing label-based hint, unchanged
```

## Seeing your screens on a real badge

```sh
app/.venv/bin/python app/tools/badge.py push preview   # your hand-driven preview app
app/.venv/bin/python app/tools/playtest.py             # plays a whole game by itself
app/.venv/bin/python app/tools/badge.py shot -o x.png  # screenshot any time
```

- `playtest.py` saves a screenshot of every screen to `app/dist/shots/`, so you
  can check your designs without photographing the badge.
- The badge **sleeps when it sits on the launcher**; a sleeping badge ignores USB
  entirely. Wake it by hand (button press, or off and on) before pushing.
- Don't touch the badge while a playtest runs: real presses mix with the fake ones.

## Before you push

1. `for t in goose preview diag; do app/.venv/bin/python app/tools/badge.py build $t; done`
2. `lua app/tools/test.lua` must print ALL TESTS PASSED. It checks that `ui.lua`
   still provides `init`, `show`, `set_time`, `touch`, `tick` and survives every
   screen, stage and edge value. If it fails on `ui.lua`, fix `ui.lua`.
3. `git pull --rebase` first; we share the `feat/badge-app` branch.

`game.lua` is Akshat's file. If a screen needs something the contract doesn't
provide (a new field, a new call), ask him and it changes on both sides at once,
including the contract docs and the tests.
