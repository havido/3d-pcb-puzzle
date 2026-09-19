"""kicad2cad command line.

    kicad2cad board.kicad_pcb --summary [--json]     # what was read
    kicad2cad board.kicad_pcb -o out/board/          # + preview.png (phase 2)

Building the 3D board (3MF/STL) arrives in phase 3 (docs/kicad2cad-plan.md).
"""
import argparse
import json
import sys
import time
from pathlib import Path

from .export import write_preview
from .parse import ParseError, load
from .shapes import to_board2d
from .summary import format_summary, summarize


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="kicad2cad", description="KiCad board -> 3D-printable 3DPCB board")
    ap.add_argument("board", help="path to a .kicad_pcb file")
    ap.add_argument("--summary", action="store_true", help="print what was read from the board")
    ap.add_argument("--json", action="store_true", help="with --summary: print JSON instead of text")
    ap.add_argument("-o", "--out", type=Path, help="output folder (writes preview.png)")
    ap.add_argument("--layer", default="F.Cu", help="copper layer to show/convert (default F.Cu)")
    ap.add_argument("--chord", type=float, default=0.02, help="max error in mm when approximating curves (default 0.02)")
    args = ap.parse_args(argv)

    if not args.summary and args.out is None:
        ap.error("nothing to do: use --summary and/or -o OUT (3D output arrives in phase 3)")
    t0 = time.perf_counter()
    try:
        board = load(args.board, arc_chord_mm=args.chord)
    except (OSError, ParseError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    if args.layer not in board.copper_layers:
        print(f"error: {args.layer} is not a copper layer of this board ({', '.join(board.copper_layers)})", file=sys.stderr)
        return 1
    b2d = to_board2d(board, chord=args.chord)
    s = summarize(board, b2d)
    s["seconds"] = round(time.perf_counter() - t0, 2)

    if args.summary:
        print(json.dumps(s, indent=1) if args.json else format_summary(s))
    if args.out is not None:
        preview = write_preview(b2d, args.out / "preview.png", layer=args.layer)
        print(f"wrote {preview}")
    if not args.json:
        print(f"done in {s['seconds']} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
