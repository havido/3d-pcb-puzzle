# Badge app: the goose Operation game

This folder is the software that runs **on the hacker badge**: the game logic and the screens. The root `CLAUDE.md` covers the whole project; this file covers only `app/`. Work here doesn't touch the generator, prints or dock, and they don't touch this.

- **Game logic** (input, state machine, countdown, LEDs): @Akshat-Kalra. Tickets #20–#23.
- **Screens and animations** (UI, sprites, goose map): @talfee. Her handoff notes: `goose/UI_NOTES.md`. Tickets #13, #14, #16, #27, #30. Her Canva designs are in `assets/`.
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

This is the real, finished goose board (goose v3; see `goose/README.md` and the root `CLAUDE.md` "Circuit (final...)" / "Goose layout" / "Current board" bullets). The goose plate covers most of the D-pad and wires its own copper nets onto three of those lines via pogo pins; the tweezers are tethered to badge GND. Touching copper = that button is pressed. The game sees ordinary `on_button` events: **no custom firmware**.

| Badge button | Board line | Goose net | Game meaning |
|---|---|---|---|
| `RIGHT` | BTN_3 (SW3) | PENALTY (head/neck/back trace + breast/belly trace, joined) | touch → time penalty |
| `UP` | BTN_2 (SW2) | GOAL_1 (tail loop) | touch → advance to stage `"goal2"` |
| `LEFT` | BTN_4 (SW4) | GOAL_2 (belly loop) | touch during `"goal2"` → win |
| n/a | SW8 GND pad | GND | tweezers tether |

- **This mapping is measured, not inferred** — it is how goose v3 is actually wired — so it's final; nothing may hard-code a button outside the one `LINES` table in `game.lua`.
- **The plate covers SW2, SW3, SW4, SW5, SW8 and SW10**, each with a relief pocket in the board back so it can never be held down. Only two switches are exposed through cut-outs: **SW7 (HOME)**, which the firmware intercepts before it reaches the app (default HOME-exit behaviour — not `confirm_home=1`, which pauses ticks but not `badge.sys.ms()`, breaking a countdown), and **SW6 (SW_HPM)**, the only button the player can actually press.
- **We don't yet know which `badge.input.BUTTON` constant SW6 reports.** Candidates are A, B and AUX1. `game.lua`'s `START_BUTTONS` table accepts any of the three as start/retry rather than guessing one; the diagnostic app on a real badge will confirm which one SW6 actually is, and then this table can be narrowed.
- **PENALTY has a 10 µF cap to GND** (see the root `CLAUDE.md`) to stretch brief touches so the button scan doesn't miss them. The cap is still charging for a moment after boot, so `game.lua` ignores all three goose lines for `INPUT_GRACE_MS` (a named constant, 500 ms) after the app starts and again for the first `INPUT_GRACE_MS` of every round.
- **Scraping PENALTY produces bursts of press/release events.** Count one penalty, then ignore PENALTY for a lockout (starting value 500 ms, a named constant) before it can count again.
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
    ui.lua           talfee: every widget and animation
    img/*.png        goose sprites etc.; converted to .bin at build time
  tools/badge.py     build / bundle / push / PNG->.bin
  tools/test.lua     headless tests (mock badge, badge-like sandbox)
  dist/              build output (git-ignored)
```

- **One owner per file.** `game.lua` never creates widgets; `ui.lua` never reads buttons or the clock for game rules. They meet only through the contract below.
- Every tunable number (round time, penalty, lockout, LED colours) is a named constant at the top of `game.lua`.

## Workflow

```sh
python3 -m venv app/.venv && app/.venv/bin/pip install -r app/tools/requirements.txt   # once
app/.venv/bin/python app/tools/badge.py build goose     # or diag
lua app/tools/test.lua                                   # needs all three built
app/.venv/bin/python app/tools/badge.py push goose       # upload over USB, no IDE needed
app/.venv/bin/python app/tools/badge.py img in.png app/goose/img/name.bin --size 56x56   # or drop PNGs in img/
```

- **push** needs the badge on USB (badge off → plug → on, don't hold Start) and the IDE tab closed, because the IDE holds the serial port. It uses the IDE's own console protocol (`put`, `reload`) and uploads images too. **Verified on a real badge 2026-09-19.**
- `badge.py logs [--seconds N] [--out FILE] [--grep TEXT]` prints the badge's USB serial console (every `badge.sys.log(...)` line, plus Lua tracebacks) in the terminal instead of the web IDE, timestamped and non-interactively runnable — this is also how to capture #20 touch-timing data from the diag app (`down UP t=...` / `up UP t=... held=...`). It holds the serial port like `push` does, so stop it (Ctrl-C, or use `--seconds`) before running `push`.
- **No terminal?** `build` also writes `app/dist/<slug>.lua`, one file for the IDE's **Import app** (code only, no images). Its line numbers differ from the sources; `build` prints where each file starts.
- Images: widgets reference them by file name, e.g. `badge.ui.image(parent, "goose_start.bin")` for `img/goose_start.png`. RGB565A8 is 3 bytes per pixel and the app has 64 KiB **in total**, so keep sprites small; `build` warns when over budget.
- Run `lua app/tools/test.lua` before pushing. The rules tests drive `game.lua` through a fake ui, so they don't break when screens change.

### Playtest on the badge

`app/.venv/bin/python app/tools/playtest.py [--port PORT] [--slow]` is an end-to-end,
on-hardware playtest: it builds and pushes `goose`, opens "Goose Doctor" from the
launcher, and scripts a full round over the console, asserting on `uitree` label
texts and console log lines. It saves one screenshot per distinct screen to
`app/dist/shots/`. `--slow` also runs the ~60 s timeout-failure scenario;
without it, the run takes well under a minute.

- **`press` only taps** (PRESSED then RELEASED a few ms later) -- the console has
  no way to hold a button down, but `game.lua`'s rules don't need a hold any
  more (a touch is a touch), so `playtest.py` drives the whole state machine
  with taps directly, with no test-only knobs to set or restore. It does need
  to respect `INPUT_GRACE_MS` (500 ms): it waits past the grace window before
  the first touch of each round, since the game itself ignores goose-line
  touches until then (the PENALTY cap is still charging).
- `app/tools/badge.py`'s `Session` (used by `playtest.py` and by the `ui` /
  `shot` / `press` / `open` CLI subcommands) is a `Console` plus `cmd` /
  `press` / `uitree` / `texts` / `shot` / `open_app`. Every call has a hard
  timeout (5 s default, 10 s for `shot`) -- it never retries in a loop against
  an unresponsive port.
- **Safety allowlist.** Only send `press`, `uitree`, `shot`, `apps`, `help`,
  `heap`, `ls`, `cat`, and the `push` flow (`mkdir` / `put` / `reload`) to the
  badge console. Never
  `rm`, `factory_reset`, `prov`, `debug`, `appmode`, `seedall`, `badge_token`,
  `badge_profile`, `card`, `ripple`, `sponsormap`, `reboot`, `chess`,
  `blindbox_response`, `radio`, or anything else -- this badge is irreplaceable
  hardware. Open the serial port once per run and reuse it; leave a couple of
  seconds between separate runs.
- **The badge sleeps when idle outside an app** (launcher / "My Badge" screen), and a sleeping badge's console is completely silent: no `badge> ` prompt, not even an echo. `press` can't wake it (it goes through the console). Wake it by hand (a button press on the badge; if that doesn't do it, switch it off and on), then run `push` / `playtest` straight away. Apps with `wake_lock=1` (Goose Doctor, Goose Diag) keep it awake, so an unattended badge should be left inside one. If a command times out, stop (don't retry or reopen the port), close the port, and ask for the badge to be woken.
- Don't touch the badge while a playtest runs: real presses mix with the injected ones, and a power cycle mid-run shows up as `Device not configured`.

## Contract between `game.lua` and `ui.lua` (see issue #40)

The full spec (argument ranges, when each call happens) is the header comment of `goose/ui.lua`. Summary:

```lua
-- game.lua calls these; ui.lua implements them.
ui.init(root)              -- build every widget once, in on_enter
ui.show(screen, info)      -- "start" | "operating" | "success" | "failure"
                           -- info = { time_left_ms >= 0, stage "goal1" | "goal2",
                           --          best_ms (nil = no best yet) }
                           -- also called again on "operating" when the stage changes
ui.set_time(time_left_ms)  -- every 100 ms while operating, and at once on a touch
ui.touch(zone)             -- always 1 (one PENALTY net): flinch/flash; at most once per 500 ms
ui.tick(now_ms)            -- every ~20 ms; advance animations, return within a few ms
```

`game.lua` implements `start(ui, now)`, `tick(now)`, `button(button, kind, now)`, `stop()`, called from `main.lua`.

Buttons: the one exposed, usable button (SW6; its `badge.input.BUTTON` constant isn't confirmed yet, so `game.lua` accepts any of A / B / AUX1, see "How the goose talks to the badge") is Start/Retry. HOME always exits (default firmware behaviour, intercepted before the app sees it) -- there is no quit button. `ui.lua` never reads buttons; the game's LEDs belong to `game.lua`.

**`lua app/tools/test.lua` enforces the contract.** It checks that `ui.lua` has all five functions and survives every screen, stage and edge value (no best time, 0 ms). If it fails on `ui.lua`, fix `ui.lua`; don't loosen the test.

**Changing the contract needs both of us.** Then, in the same commit, update the header of `ui.lua`, this section, `game.lua`, and the contract test in `tools/test.lua`.

## Working rules

- Branch `feat/badge-app` (or a branch off it); PRs into `main`.
- Test on the badge after every change. Note the firmware version with any timing result.
- Measured facts (button mapping, scan rate, firmware version, lockout that feels right) go into this file, replacing the guesses above.
