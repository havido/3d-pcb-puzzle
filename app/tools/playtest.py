#!/usr/bin/env python3
"""End-to-end playtest of Goose Doctor on a real badge.

  app/.venv/bin/python app/tools/playtest.py [--port PORT] [--slow]

Builds + pushes `goose`, opens "Goose Doctor" from the launcher, and runs
scripted scenarios from game.lua, asserting on uitree label texts (ui.lua's
screens) and console log lines, printing PASS/FAIL per check. Saves a
screenshot of each distinct screen to app/dist/shots/.

The badge console's `press` only taps -- PRESSED then RELEASED a few ms
later, see the Session docstring in badge.py -- it cannot hold a button the
way a real seated organ does. Two things in game.lua need a hold:
  - REQUIRE_SEATED: A only starts a round with organ A held in its seat.
  - a seat must SETTLE (stay in one state) for SEAT_SETTLE_MS before it
    counts, so a tap's real, brief "seated" instant is never sampled.
This script tests the refused-start rule with the *real* defaults (a tap
can never hold a seat, so it's always refused -- exactly what should
happen), then sets game.lua's test knobs (`config goose_doctor t_seated 0`
and `t_settle_ms 0`) to exercise the rest of the state machine with taps,
and restores the real defaults in `finally`, even on failure. This means
the *hold* requirement itself -- that a momentary touch must NOT start a
round or count as delivered -- is not exercised end-to-end by this script
beyond that one refused-start check; a real seated organ (or a manual test
holding a button on the badge) is the only way to confirm the hold timing.
"""
import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import badge  # noqa: E402

SLUG = "goose_doctor"
SHOTS = badge.DIST / "shots"
DEFAULT_SEATED, DEFAULT_SETTLE = 1, 150

passed = failed = 0
_shot_taken = set()


def check(cond, msg):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS: {msg}")
    else:
        failed += 1
        print(f"  FAIL: {msg}")
    return cond


def snap(s, name):
    """Save one screenshot per distinct screen name."""
    if name in _shot_taken:
        return
    _shot_taken.add(name)
    SHOTS.mkdir(parents=True, exist_ok=True)
    try:
        path = SHOTS / f"{name}.png"
        s.shot().save(path)
        print(f"  shot: {path}")
    except Exception as e:
        print(f"  shot FAILED ({name}): {e}")


def timer_ms(texts):
    """Find the "MM:SS:CC" timer label among `texts` and return milliseconds."""
    for t in texts:
        m = re.fullmatch(r"(\d{2}):(\d{2}):(\d{2})", t)
        if m:
            mm, ss, cc = (int(x) for x in m.groups())
            return (mm * 60 + ss) * 1000 + cc * 10
    return None


def set_knobs(s, seated, settle_ms):
    s.cmd(f"config {SLUG} t_seated {seated}")
    s.cmd(f"config {SLUG} t_settle_ms {settle_ms}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--port", help="serial port (default: first /dev/cu.usbmodem*)")
    ap.add_argument("--slow", action="store_true",
                     help="also run the ~60s timeout-failure scenario")
    a = ap.parse_args()
    port = a.port or badge.find_port()

    print("building + pushing goose ...")
    badge.push("goose", port)

    s = None
    silent = False
    try:
        s = badge.Session(port)   # can itself time out if the badge is silent
        # Defensive: a previous run that crashed before its own `finally`
        # could have left the knobs non-default.
        set_knobs(s, DEFAULT_SEATED, DEFAULT_SETTLE)

        print("\n=== refused start (real defaults: A must hold organ A seated) ===")
        s.open_app("Goose Doctor")
        t = s.texts()
        check("welcome to" in t and "Goose Doctor" in t, "opens on the start screen")
        snap(s, "start")
        s.press("A")   # a tap can never leave a seat "held", so this must refuse
        t = s.texts()
        check("welcome to" in t, "A refuses to start: still on the start screen")

        print("\n=== switching to test knobs (t_seated=0, t_settle_ms=0) ===")
        s.press("B")   # contract: B quits from the start screen -> launcher
        set_knobs(s, 0, 0)
        s.open_app("Goose Doctor")

        print("\n=== start ===")
        s.press("A")
        t = s.texts()
        check("Operating..." in t, "A starts a round")
        check("Remove the organ" in t, "starts on the remove stage")
        t0 = timer_ms(t)
        check(t0 is not None and t0 >= 59000, f"timer starts near 60:00:00 (got {t0})")
        snap(s, "operating_remove")

        print("\n=== wall touch costs 5 s ===")
        before = timer_ms(s.texts())
        s.press("Up")
        touched = s.texts()
        after = timer_ms(touched)
        check(before is not None and after is not None and before - after >= 4900,
              f"touching wall 1 costs ~5 s ({before} -> {after})")
        check(any(x.startswith("OUCH! wall 1") for x in touched),
              "flash shows which wall (best-effort: the flash is only up 250ms)")

        print("\n=== lockout: a second scrape inside the window costs nothing more ===")
        s.press("Up")
        after2 = timer_ms(s.texts())
        check(after2 is not None and after - after2 < 500,
              f"lockout holds ({after} -> {after2})")

        print("\n=== seat B before removal does nothing ===")
        s.press("Right")
        t = s.texts()
        check("Remove the organ" in t, "seat B (deliver) is ignored before organ A is removed")

        print("\n=== remove organ A -> deliver stage ===")
        s.press("Left")
        t = s.texts()
        check("Deliver the new organ" in t, "lifting organ A moves to the deliver stage")
        snap(s, "operating_deliver")

        print("\n=== deliver -> SUCCESS ===")
        s.press("Right")
        t = s.texts()
        check("SUCCESS!" in t, "seating organ B wins")
        check(any(x.startswith("Best ") for x in t), "a best time is shown")
        snap(s, "success")

        if a.slow:
            print("\n=== timeout failure (--slow, ~60 s) ===")
            s.press("A")   # retry (t_seated=0, so no seating needed)
            check("Remove the organ" in s.texts(), "retry starts a fresh round")
            print("  waiting for the timer to run out ...")
            deadline = time.time() + 65
            timed_out = False
            while time.time() < deadline:
                if "FAILURE!" in s.texts():
                    timed_out = True
                    break
                time.sleep(2)
            check(timed_out, "running out of time fails")
            if timed_out:
                snap(s, "failure")

        print("\n=== B quits to the launcher ===")
        s.press("B")
    except TimeoutError as e:
        # The badge went silent (no "badge> " prompt): per app/CLAUDE.md, stop
        # -- don't retry in a loop. Report what we can, then fall through to
        # the same best-effort cleanup as any other failure.
        silent = True
        last = s.last_cmd if s is not None else "(Session handshake)"
        print(f"\nBADGE WENT SILENT: no prompt after command {last!r}\n  {e}")
    finally:
        print("\nrestoring default knobs ...")
        if s is None:
            print("  WARNING: never got a session, nothing to restore/close")
        else:
            try:
                set_knobs(s, DEFAULT_SEATED, DEFAULT_SETTLE)
            except Exception as e:
                print(f"  WARNING: failed to restore knobs: {e}")
            try:
                s.press("Home")   # make sure we land on the launcher regardless
            except Exception as e:
                print(f"  WARNING: failed to return Home: {e}")
            try:
                s.s.close()
            except Exception as e:
                print(f"  WARNING: failed to close the port: {e}")

    print(f"\n{passed} passed, {failed} failed")
    if silent:
        print("badge console went silent; a power cycle is needed before the next run")
        sys.exit(2)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
