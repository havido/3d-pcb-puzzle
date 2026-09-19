# Badge app: the goose Operation game

This folder is the software that runs **on the hacker badge**: the game logic and the screens. The root `CLAUDE.md` covers the whole project; this file covers only `app/`. Work here doesn't touch the generator, prints or dock, and they don't touch this.

- **Game logic** (input, state machine, countdown, LEDs): Akshat-Kalra. Tickets #18–#23.
- **Screens and animations** (UI, sprites, goose map): teammate. Tickets #13, #14, #16, #27, #30.
- Stretch: #37 best-times table, #36 easter eggs.

## Platform (read `BADGE_API.md` before writing badge code)

`BADGE_API.md` is the organisers' official guide, copied from https://badge.hackthenorth.com/ide/README.md on 2026-09-19. **Don't edit it**; re-download it if the IDE changes. Use only the APIs it documents.

- **Lua 5.x in a sandbox:** no `os`, `io`, `pcall`, `setmetatable`, `coroutine` or `load`. Manifest `api=2`.
- **Lifecycle:** global `on_enter(root)`, `on_tick()` (~20 ms), `on_button(button, kind)`, `on_exit()`. Never `local function on_enter`.
- **Deploy:** the web IDE (https://badge.hackthenorth.com/ide/, Chrome/Edge) → **Import app** (paste the single-file app) → **Connect** → **Push**. Switch the badge off before plugging in USB, and don't hold Start. The IDE is an uploader, **not a simulator**: every test runs on a real badge.
- **Limits:** 48 KiB Lua heap, 64 KiB `main.lua`, 512 widgets, 32 store keys. No canvas: screens are built from `badge.ui` widgets (`label box bar arc line image …`); `line` takes ≤ 128 points; images are `.bin` files made by the IDE.
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
  CLAUDE.md       this file
  BADGE_API.md    official API guide (read-only copy)
  diag/           #19 diagnostic app: all lines live + press timings
  goose/          the game
    main.lua      lifecycle callbacks; wires game and ui together
    game.lua      Akshat: config table, input layer, state machine, timer, LEDs
    ui.lua        teammate: every widget and animation
```

- **One owner per file.** `game.lua` never creates widgets; `ui.lua` never reads buttons or the clock for game rules. They meet only through the contract below.
- Every tunable number (round time, penalty, lockout, LED colours) is a named constant at the top of `game.lua`.
- Keep a manifest header (`--[==[badge-app … ]==]`, see `BADGE_API.md`) at the top of each app's `main.lua`, so the app can be pasted into **Import app**. Multi-file apps need each module added in the IDE with **+**; if that gets tedious, add a small script that inlines the modules into one importable file.

## Contract between `game.lua` and `ui.lua` (draft: agree before building)

```lua
-- game.lua calls these; ui.lua implements them.
ui.init(root)                -- build every widget once (in on_enter)
ui.show(screen, info)        -- screen: "idle" | "remove" | "deliver" | "win" | "lose"
                             -- info: { time_left_ms, penalties, best_ms }
ui.set_time(time_left_ms)    -- countdown changed (at most every 100 ms)
ui.touch(zone)               -- zone: 1 | 2; play the flinch, light that wall on the map
ui.tick(now_ms)              -- advance animations; must return in a few ms
```

Change this contract only when both of us agree, and update this section in the same commit.

## Working rules

- Branch `feat/badge-app` (or a branch off it); PRs into `main`.
- Test on the badge after every change. Note the firmware version with any timing result.
- Measured facts (button mapping, scan rate, firmware version, lockout that feels right) go into this file, replacing the guesses above.
