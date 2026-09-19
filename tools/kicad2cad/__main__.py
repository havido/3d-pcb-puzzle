"""kicad2cad command line.

    kicad2cad board.kicad_pcb --summary [--json]                  # what was read
    kicad2cad board.kicad_pcb -o out/board [--recipe params/3dpcb.yaml]
        # → board.stl, board.3mf, preview.png, plot_1to1.pdf, layers/*.svg, report.json
"""
import argparse
import json
import sys
import time
from pathlib import Path

from .build import RecipeError, build, load_recipe, prepare
from .export import write_meshes, write_plot_1to1, write_preview, write_report, write_svgs
from .parse import ParseError, load
from .shapes import to_board2d
from .summary import format_summary, summarize


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="kicad2cad", description="KiCad board -> 3D-printable 3DPCB board")
    ap.add_argument("board", help="path to a .kicad_pcb file")
    ap.add_argument("-o", "--out", type=Path, help="output folder for the printable board and previews")
    ap.add_argument("--recipe", type=Path, help="YAML with the tunable numbers (default: built-in, see params/3dpcb.yaml)")
    ap.add_argument("--layer", help="copper layer to raise (overrides the recipe's copper_layer)")
    ap.add_argument("--summary", action="store_true", help="print what was read from the board")
    ap.add_argument("--json", action="store_true", help="with --summary: print JSON instead of text")
    args = ap.parse_args(argv)

    if not args.summary and args.out is None:
        ap.error("nothing to do: use -o OUT to build the board, and/or --summary")
    t0 = time.perf_counter()
    try:
        recipe = load_recipe(args.recipe)
        if args.layer:
            recipe.copper_layer = args.layer
        board = load(args.board, arc_chord_mm=recipe.arc_chord_mm)
        if recipe.copper_layer not in board.copper_layers:
            raise RecipeError(f"{recipe.copper_layer} is not a copper layer of this board ({', '.join(board.copper_layers)})")
        b2d, effects = prepare(to_board2d(board, chord=recipe.arc_chord_mm, include_zones=recipe.include_zones,
                                          include_copper_graphics=recipe.include_copper_graphics), recipe)
    except (OSError, ParseError, RecipeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    s = summarize(board, b2d)
    s["seconds"] = round(time.perf_counter() - t0, 2)

    if args.out is not None:
        bld = build(b2d, recipe)
        files = write_meshes(bld.mesh, args.out)
        files["preview"] = write_preview(b2d, args.out / "preview.png", layer=recipe.copper_layer)
        files["plot_1to1"] = write_plot_1to1(b2d, args.out / "plot_1to1.pdf", layer=recipe.copper_layer)
        for svg in write_svgs(b2d, args.out / "layers", layer=recipe.copper_layer):
            files[f"svg:{svg.stem}"] = svg
        seconds = time.perf_counter() - t0
        report = write_report(args.out / "report.json", s, recipe, bld, effects, files, seconds)
        s = json.loads(report.read_text())

    if args.summary:
        print(json.dumps(s, indent=1) if args.json else format_summary(s))
    if args.out is not None and not args.json:
        b = s["build"]
        print(f"\nwrote {args.out}/: board.stl, board.3mf, preview.png, plot_1to1.pdf, layers/*.svg, report.json")
        for w in s["warnings"][len(board.warnings):]:
            print(f"  ! {w}")
        closed = b["watertight"] and b["stl_file_watertight"]
        print(f"KiCad → printable board in {b['seconds']} s · {b['volume_mm3']:.0f} mm³ · "
              f"{'watertight' if closed else 'NOT WATERTIGHT (check report.json)'} · {b['triangles']} triangles")
    return 0


if __name__ == "__main__":
    sys.exit(main())
