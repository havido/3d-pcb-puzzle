#!/usr/bin/env python3
"""End-to-end playtest of Goose Doctor on a real badge.

  app/.venv/bin/python app/tools/playtest.py [--port PORT] [--slow]

Builds + pushes `goose`, opens "Goose Doctor" from the launcher, and runs
scripted scenarios from game.lua, asserting on uitree label texts (ui.lua's
screens) and console log lines, printing PASS/FAIL per check. Saves a
screenshot of each distinct screen to app/dist/shots/.

The badge console's `press` only taps -- PRESSED then RELEASED a few ms
later, see the Session docstring in badge.py. game.lua's rules don't need a
hold any more (a touch is a touch), so this script drives the whole state
machine with taps directly.

game.lua ignores the goose lines (PENALTY/GOAL_1/GOAL_2) for
INPUT_GRACE_MS = 500 ms after the app starts and again for the first 500 ms
of every round, because the PENALTY net's 10 uF cap is still charging. This
script waits past that window (GRACE_S, with margin for console round-trip
time) before the first goose-line touch of each round.

The one exposed, usable button is SW6, whose real badge.input.BUTTON
constant isn't confirmed yet (see app/CLAUDE.md); game.lua accepts any of
A, B or AUX1 as start/retry. This script presses "A" throughout -- the
console's `press` injects a button event directly, so it works regardless
of which constant SW6 turns out to be.
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
GRACE_S = 0.7   # > game.lua's INPUT_GRACE_MS (500 ms), with margin

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

        print("\n=== start screen ===")
        s.open_app("Goose Doctor")
        t = s.texts()
        check("welcome to" in t and "Goose Doctor" in t, "opens on the start screen")
        snap(s, "start")

        print("\n=== start ===")
        s.press("A")
        t = s.texts()
        check("Operating..." in t, "A starts a round")
        check(any("TAIL" in x for x in t), "starts on the goal1 (tail) stage")
        t0 = timer_ms(t)
        check(t0 is not None and t0 >= 59000, f"timer starts near 60:00:00 (got {t0})")
        snap(s, "operating_goal1")

        print(f"\n=== waiting {GRACE_S}s past the input grace window ===")
        time.sleep(GRACE_S)

        print("\n=== PENALTY touch costs 5 s ===")
        before = timer_ms(s.texts())
        s.press("Right")
        touched = s.texts()
        after = timer_ms(touched)
        check(before is not None and after is not None and before - after >= 4900,
              f"touching PENALTY costs ~5 s ({before} -> {after})")
        check(any(x.startswith("OUCH") for x in touched),
              "flash shows the touch (best-effort: the flash is only up 250ms)")

        print("\n=== lockout: a second scrape inside the window costs nothing more ===")
        s.press("Right")
        after2 = timer_ms(s.texts())
        check(after2 is not None and after - after2 < 500,
              f"lockout holds ({after} -> {after2})")

        print("\n=== GOAL_2 before GOAL_1 does nothing ===")
        s.press("Left")
        t = s.texts()
        check(any("TAIL" in x for x in t), "GOAL_2 is ignored before GOAL_1 (still stage goal1)")

        print("\n=== GOAL_1 (tail) -> stage goal2 ===")
        s.press("Up")
        t = s.texts()
        check(any("BELLY" in x for x in t), "touching GOAL_1 moves to the goal2 (belly) stage")
        snap(s, "operating_goal2")

        print("\n=== GOAL_2 (belly) -> SUCCESS ===")
        s.press("Left")
        t = s.texts()
        check("SUCCESS!" in t, "touching GOAL_2 in stage goal2 wins")
        check(any(x.startswith("Best ") for x in t), "a best time is shown")
        snap(s, "success")

        if a.slow:
            print("\n=== timeout failure (--slow, ~60 s) ===")
            s.press("A")   # retry
            check(any("TAIL" in x for x in s.texts()), "retry starts a fresh round")
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

        print("\n=== leaving on the launcher (HOME exits) ===")
        s.press("Home")
    except TimeoutError as e:
        # The badge went silent (no "badge> " prompt): per app/CLAUDE.md, stop
        # -- don't retry in a loop. Report what we can, then fall through to
        # the same best-effort cleanup as any other failure.
        silent = True
        last = s.last_cmd if s is not None else "(Session handshake)"
        print(f"\nBADGE WENT SILENT: no prompt after command {last!r}\n  {e}")
    finally:
        if s is None:
            print("\n  WARNING: never got a session, nothing to close")
        else:
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
