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
