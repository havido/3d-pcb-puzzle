"""One conversion run, reported stage by stage.

This is the only place the web service touches kicad2cad. A future AI layer calls the
same function through the same recipe schema, so it can never do anything the UI can't.
"""
import dataclasses
import time
from pathlib import Path
from typing import Callable

from kicad2cad.build import Recipe, RecipeError, build, prepare
from kicad2cad.export import write_meshes, write_plot_1to1, write_preview, write_report, write_svgs
from kicad2cad.parse import ParseError, load
from kicad2cad.shapes import to_board2d
from kicad2cad.summary import summarize

# What the UI renders as controls, and what an AI layer would get as a JSON schema.
RECIPE_FIELDS = [
    dict(name="copper_layer", type="choice", choices=["F.Cu", "B.Cu"], default="F.Cu",
         label="Copper layer", help="Which layer becomes raised copper. The other is ignored (single-sided)."),
    dict(name="base_thickness", type="number", default=2.0, min=0.4, max=8.0, step=0.2, unit="mm",
         label="Base thickness", help="Plastic under the copper."),
    dict(name="copper_raise", type="number", default=0.6, min=0.2, max=2.0, step=0.1, unit="mm",
         label="Copper height", help="How far the copper stands above the base."),
    dict(name="min_drill", type="number", default=1.0, min=0.4, max=3.0, step=0.1, unit="mm",
         label="Smallest hole", help="Holes narrower than this are handled by the rule below."),
    dict(name="small_drill", type="choice", choices=["keep", "enlarge", "skip"], default="keep",
         label="Small holes", help="Enlarge them to the minimum, leave them out, or keep them as drawn."),
    dict(name="alignment_diameter", type="number", default=3.0, min=2.0, max=8.0, step=0.5, unit="mm",
         label="Pin hole size", help="Holes for the cutter plate's alignment pins."),
    dict(name="alignment_clearance", type="number", default=3.0, min=1.0, max=8.0, step=0.5, unit="mm",
         label="Pin clearance", help="Space kept free around each pin hole."),
    dict(name="alignment_holes_on", type="bool", default=False,
         label="Add pin holes", help="Place two alignment holes automatically, clear of copper."),
    dict(name="arc_chord_mm", type="number", default=0.02, min=0.005, max=0.2, step=0.005, unit="mm",
         label="Curve accuracy", help="Largest gap allowed between a curve and its straight-line approximation."),
]
DEFAULTS = {f["name"]: f["default"] for f in RECIPE_FIELDS}


def recipe_from(values: dict) -> Recipe:
    """UI values -> a validated kicad2cad Recipe. Raises RecipeError for bad input."""
    v = {**DEFAULTS, **(values or {})}
    unknown = sorted(set(v) - set(DEFAULTS))
    if unknown:
        raise RecipeError(f"unknown setting(s): {', '.join(unknown)}")
    r = Recipe(
        copper_layer=v["copper_layer"],
        base_thickness=float(v["base_thickness"]),
        copper_raise=float(v["copper_raise"]),
        arc_chord_mm=float(v["arc_chord_mm"]),
        min_drill=float(v["min_drill"]),
        small_drill=v["small_drill"],
        alignment_holes={"diameter": float(v["alignment_diameter"]), "positions": "auto",
                         "clearance": float(v["alignment_clearance"])} if v["alignment_holes_on"] else {},
    )
    r.validate()
    return r


class Stages:
    def __init__(self, on_stage: Callable[[dict], None] | None):
        self.on_stage, self.items, self.t0 = on_stage, [], time.perf_counter()

    def done(self, name: str, label: str, detail: str):
        item = {"name": name, "label": label, "detail": detail, "seconds": round(time.perf_counter() - self.t0, 2)}
        self.items.append(item)
        if self.on_stage:
            self.on_stage(item)


def run(board_path: Path, values: dict, out_dir: Path, on_stage=None) -> dict:
    """Convert one board. Returns the result the API hands to the browser."""
    recipe = recipe_from(values)
    out_dir.mkdir(parents=True, exist_ok=True)
    st = Stages(on_stage)

    board = load(board_path, arc_chord_mm=recipe.arc_chord_mm)
    if recipe.copper_layer not in board.copper_layers:
        raise RecipeError(f"{recipe.copper_layer} is not a copper layer of this board "
                          f"({', '.join(board.copper_layers)})")
    tracks = sum(1 for t in board.tracks if t.layer == recipe.copper_layer)
    st.done("parse", "Read the KiCad file",
            f"{tracks} tracks, {len(board.pads)} pads, {len(board.vias)} vias, {len(board.drills)} holes")

    b2d = to_board2d(board, chord=recipe.arc_chord_mm)
    copper = b2d.merged[recipe.copper_layer]
    st.done("shapes", "Turned it into 2D shapes",
            f"{copper.area:.0f} mm² of copper in {len(copper.geoms)} piece(s)")

    b2d, effects = prepare(b2d, recipe)
    bits = []
    if effects["drills_enlarged"]:
        bits.append(f"{effects['drills_enlarged']} holes enlarged")
    if effects["drills_skipped"]:
        bits.append(f"{effects['drills_skipped']} holes skipped")
    if effects["alignment_holes"]:
        bits.append(f"{len(effects['alignment_holes'])} alignment pins placed")
    st.done("prepare", "Applied the settings", ", ".join(bits) or "nothing to change")

    bld = build(b2d, recipe)
    st.done("build", "Built the 3D board",
            f"{bld.mesh.volume:.0f} mm³, {len(bld.mesh.faces)} triangles, "
            f"{'watertight' if bld.mesh.is_watertight else 'NOT watertight'}")

    files = write_meshes(bld.mesh, out_dir)
    files["preview"] = write_preview(b2d, out_dir / "preview.png", layer=recipe.copper_layer)
    files["plot_1to1"] = write_plot_1to1(b2d, out_dir / "plot_1to1.pdf", layer=recipe.copper_layer)
    for svg in write_svgs(b2d, out_dir / "layers", layer=recipe.copper_layer):
        files[f"svg:{svg.stem}"] = svg
    summary = summarize(board, b2d)
    report_path = write_report(out_dir / "report.json", summary, recipe, bld, effects, files,
                               time.perf_counter() - st.t0)
    st.done("export", "Wrote the files", "STL, 3MF, preview, 1:1 PDF, SVG layers, report")

    import json
    report = json.loads(report_path.read_text())
    b = report["build"]
    return {
        "recipe": dataclasses.asdict(recipe),
        "settings": {**DEFAULTS, **(values or {})},
        "stages": st.items,
        "seconds": st.items[-1]["seconds"],
        "warnings": report["warnings"],
        "markers": [{"x": x, "y": y, "message": m} for x, y, m in b2d.markers],
        "alignment": [{"x": x, "y": y, "diameter": d} for x, y, d in b2d.alignment],
        "outline": {"bbox": summary["outline"]["bbox"], "size_mm": summary["outline"]["size_mm"]},
        "summary": {"copper": summary["copper"], "pad_shapes": summary["pad_shapes"],
                    "drills": summary["drills"], "version": summary["version"]},
        "build": {"volume_mm3": b["volume_mm3"], "triangles": b["triangles"],
                  "watertight": b["watertight"] and b["stl_file_watertight"],
                  "bounds_mm": b["bounds_mm"], "copper_area_mm2": b["copper_area_mm2"],
                  "base_area_mm2": b["base_area_mm2"], "recipe_effects": b["recipe_effects"]},
        "files": {"board.stl": "board.stl", "board.3mf": "board.3mf", "preview.png": "preview.png",
                  "plot_1to1.pdf": "plot_1to1.pdf", "report.json": "report.json",
                  **{f"layers/{p.name}": f"layers/{p.name}" for p in sorted((out_dir / "layers").glob("*.svg"))}},
    }


__all__ = ["run", "recipe_from", "RECIPE_FIELDS", "DEFAULTS", "ParseError", "RecipeError"]
