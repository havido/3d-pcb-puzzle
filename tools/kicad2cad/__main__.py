"""kicad2cad command line.

    python -m kicad2cad board.kicad_pcb --summary [--json]

Building the 3D board (--recipe / -o) arrives in phase 3 (docs/kicad2cad-plan.md).
"""
import argparse
import json
import sys
import time

from .parse import ParseError, load
from .summary import format_summary, summarize


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="kicad2cad", description="KiCad board -> 3D-printable 3DPCB board")
    ap.add_argument("board", help="path to a .kicad_pcb file")
    ap.add_argument("--summary", action="store_true", help="print what was read from the board and exit")
    ap.add_argument("--json", action="store_true", help="with --summary: print JSON instead of text")
    args = ap.parse_args(argv)

    if not args.summary:
        ap.error("building the 3D board isn't implemented yet (phase 3); use --summary")
    t0 = time.perf_counter()
    try:
        board = load(args.board)
    except (OSError, ParseError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    s = summarize(board)
    s["parse_seconds"] = round(time.perf_counter() - t0, 2)
    print(json.dumps(s, indent=1) if args.json else format_summary(s) + f"\nparsed in {s['parse_seconds']} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
