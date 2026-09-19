# Badge app: the goose Operation game

This folder is the software that runs **on the hacker badge**: the game logic and the screens. The root `CLAUDE.md` covers the whole project; this file covers only `app/`. Work here doesn't touch the generator, prints or dock, and they don't touch this.

- **Game logic** (input, state machine, countdown, LEDs): @Akshat-Kalra. Tickets #20–#23.
- **Screens and animations** (UI, sprites, goose map): @talfee. Tickets #13, #14, #16, #27, #30. Her Canva designs are in `assets/`.
- How we split it: issue #40.
- Stretch: #37 best-times table, #36 easter eggs.

## Platform (read `BADGE_API.md` before writing badge code)

`BADGE_API.md` is the organisers' official guide, copied from https://badge.hackthenorth.com/ide/README.md on 2026-09-19. **Don't edit it**; re-download it if the IDE changes. Use only the APIs it documents.

- **Lua 5.x in a sandbox:** no `os`, `io`, `pcall`, `setmetatable`, `coroutine` or `load`. Manifest `api=2`.
- **Lifecycle:** global `on_enter(root)`, `on_tick()` (~20 ms), `on_button(button, kind)`, `on_exit()`. Never `local function on_enter`.
- **Deploy:** `tools/badge.py push` (see Workflow), or the web IDE (https://badge.hackthenorth.com/ide/, Chrome/Edge) → **Import app** → **Connect** → **Push**. Switch the badge off before plugging in USB, and don't hold Start. The IDE is an uploader, **not a simulator**: every test runs on a real badge.
- **Limits:** 48 KiB Lua heap, 64 KiB `main.lua`, 512 widgets, 32 store keys. No canvas: screens are built from `badge.ui` widgets (`label box bar arc line image …`); `line` takes ≤ 128 points; images are LVGL `.bin` files (`tools/badge.py` converts PNGs).
- **Deadlines depend on the firmware:** new firmware (2026-09-16+) allows 250 ms per tick and 1 s per button callback. Older firmware allows **6 ms per tick and 20 ms per button callback**. Check `badge.sys.version()` on every badge we demo with. Keep normal tick work to a few ms either way.
- **Fonts are ASCII only.** No em dashes, curly quotes or emoji in on-screen text.

## How the goose talks to the badge

The goose's copper zones are wired to the D-pad button lines; the tweezers are wired to badge GND. Touching copper = that button is pressed. The game sees ordinary `on_button` events: **no custom firmware**.

| Badge button | Board line | Game meaning | Event |
|---|---|---|---|
| `UP` | BTN_2 (SW2) | Wall zone 1 | `PRESSED` = touch → time penalty |
| `LEFT` | BTN_4 (SW4) | Seat A (organ to remove) | held = seated; `RELEASED` = picked up |
| `RIGHT` | BTN_3 (SW3) | Seat B (delivery spot) | `PRESSED` = delivered → win |
| `DOWN` | BTN_5 (SW8) | Wall zone 2 | `PRESSED` = touch → penalty (lets the screen show where) |

- **The button ↔ switch mapping is inferred from switch positions on the PCB, and the line ↔ meaning assignment is a placeholder.** Confirm both with the diagnostic app on a real badge, then fix them in **one** config table in the code. Nothing else may hard-code a button.
- **A, B, START and HOME stay free for the player.** Use the default HOME exit (not `confirm_home=1`: it pauses ticks but not `badge.sys.ms()`, which breaks a countdown).
- **Scraping a wall produces bursts of press/release events.** Count one penalty per zone, then ignore that zone for a lockout (starting value 500 ms, a named constant).
- **Missed touches (#20):** the firmware's button scan rate is undocumented. The diagnostic app measures the shortest press it sees; if brief touches are lost, the hardware fix is a ~10 µF capacitor on the wall line (see `GOOSE_GAME.txt`).
- **LEDs are 1-based:** 1 upper left, 2 upper right, 3 middle right, 4 bottom right, 5 bottom left, 6 middle left. The goose sits over the bottom half, so 4 and 5 shine through it.

## Code layout

```
app/
  CLAUDE.md          this file
  BADGE_API.md       official API guide (read-only copy)
  diag/main.lua      #19 diagnostic app (single file with its manifest header)
  goose/             the game, "Goose Doctor"
    main.lua         lifecycle callbacks only: wires a driver to ui
    game.lua         Akshat: config table, input layer, stages, timer, LEDs, best time
    preview.lua      fake driver for UI work (see below); never ships in goose_doctor
    ui.lua           talfee: every widget and animation
    img/*.png        goose sprites etc.; converted to .bin at build time
  tools/badge.py     build / bundle / push / PNG->.bin
  tools/test.lua     headless tests (mock badge, badge-like sandbox)
  dist/              build output (git-ignored)
```

- **One owner per file.** `game.lua` never creates widgets; `ui.lua` never reads buttons or the clock for game rules. They meet only through the contract below.
- Every tunable number (round time, penalty, lockout, LED colours) is a named constant at the top of `game.lua`.
- **Two apps from one folder** (`TARGETS` in `tools/badge.py`, which also holds the manifests):
  - `goose` → **Goose Doctor** (`goose_doctor`): the real game, driver = `game.lua`.
  - `preview` → **Goose UI Preview** (`goose_preview`): driver = `preview.lua`, a fake game for building screens without the goose. A next screen, LEFT previous, B / RIGHT touch wall 1 / 2, START switches stage, and a fake timer.
  - `main.lua` does `require("driver")`; the build generates `driver.lua` pointing at the right one.

## Workflow

```sh
python3 -m venv app/.venv && app/.venv/bin/pip install -r app/tools/requirements.txt   # once
app/.venv/bin/python app/tools/badge.py build goose     # or preview / diag
lua app/tools/test.lua                                   # needs all three built
app/.venv/bin/python app/tools/badge.py push goose       # upload over USB, no IDE needed
app/.venv/bin/python app/tools/badge.py img in.png app/goose/img/name.bin --size 56x56   # or drop PNGs in img/
```

- **push** needs the badge on USB (badge off → plug → on, don't hold Start) and the IDE tab closed, because the IDE holds the serial port. It uses the IDE's own console protocol (`put`, `reload`) and uploads images too. **Verified on a real badge 2026-09-19.**
- `badge.py logs [--seconds N] [--out FILE] [--grep TEXT]` prints the badge's USB serial console (every `badge.sys.log(...)` line, plus Lua tracebacks) in the terminal instead of the web IDE, timestamped and non-interactively runnable — this is also how to capture #20 touch-timing data from the diag app (`down UP t=...` / `up UP t=... held=...`). It holds the serial port like `push` does, so stop it (Ctrl-C, or use `--seconds`) before running `push`.
- **No terminal?** `build` also writes `app/dist/<slug>.lua`, one file for the IDE's **Import app** (code only, no images). Its line numbers differ from the sources; `build` prints where each file starts.
- Images: widgets reference them by file name, e.g. `badge.ui.image(parent, "goose_start.bin")` for `img/goose_start.png`. RGB565A8 is 3 bytes per pixel and the app has 64 KiB **in total**, so keep sprites small; `build` warns when over budget.
- Run `lua app/tools/test.lua` before pushing. The rules tests drive `game.lua` through a fake ui, so they don't break when screens change.

## Contract between `game.lua` and `ui.lua` (see issue #40)

The full spec (argument ranges, when each call happens) is the header comment of `goose/ui.lua`. Summary:

```lua
-- game.lua calls these; ui.lua implements them.
ui.init(root)              -- build every widget once, in on_enter
ui.show(screen, info)      -- "start" | "operating" | "success" | "failure"
                           -- info = { time_left_ms >= 0, stage "remove" | "deliver",
                           --          best_ms (nil = no best yet) }
                           -- also called again on "operating" when the stage changes
ui.set_time(time_left_ms)  -- every 100 ms while operating, and at once on a touch
ui.touch(zone)             -- 1 | 2: flinch + show which wall; at most once per zone per 500 ms
ui.tick(now_ms)            -- every ~20 ms; advance animations, return within a few ms
```

Drivers (`game.lua`, `preview.lua`) implement `start(ui, now)`, `tick(now)`, `button(button, kind, now)`, `stop()`, called from `main.lua`.

Buttons: A = Start/Retry, B = Quit (from start/success/failure), HOME always exits. `ui.lua` never reads buttons; the game's LEDs belong to `game.lua`.

**`lua app/tools/test.lua` enforces the contract.** It checks that `ui.lua` has all five functions and survives every screen, stage and edge value (no best time, 0 ms). If it fails on `ui.lua`, fix `ui.lua`; don't loosen the test.

**Changing the contract needs both of us.** Then, in the same commit, update the header of `ui.lua`, this section, `preview.lua` and `game.lua` if they use it, and the contract test in `tools/test.lua`.

## Working rules

- Branch `feat/badge-app` (or a branch off it); PRs into `main`.
- Test on the badge after every change. Note the firmware version with any timing result.
- Measured facts (button mapping, scan rate, firmware version, lockout that feels right) go into this file, replacing the guesses above.
