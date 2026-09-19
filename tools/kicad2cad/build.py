"""Phases 3–4: `Board2D` + recipe → 3D solid.

Everything is 2.5D: the base plate is the outline (minus drills) extruded to
`base_thickness`, and the copper is extruded `copper_raise` high and stacked on top.
KiCad's Y axis points down, so Y is flipped here, once: looking down on the printed
board you see what KiCad shows.

Phase 4 recipe extras, applied by `prepare` (2D) and `build` (3D):
- small_drill: drills narrower than min_drill are enlarged, skipped, or kept;
- alignment_holes: holes for the cutter plate's pins, placed clear of copper/holes/edge;
- extra_layers: user-layer shapes cut into the board (goose channels, seat pockets).

Mesh hygiene (found on the badge: its STL wasn't watertight once saved and reloaded):
- all final 2D shapes live on a 1 µm grid (GRID), so no two distinct points are closer
  than an STL's float32 coordinates can tell apart;
- shapes that touch at a single point ("pinch points", e.g. thermal-relief spokes) are
  closed with a CLOSE_EPS grow-and-shrink, turning each into a tiny neck;
- the copper sits on the base instead of starting at z = 0, so no two faces overlap;
- anything stacked on or cut into the base stays ≥ GRID inside it (`inside`), so its edges
  never touch the base's edges at a single point (found with enlarged drills).
"""
import dataclasses
from dataclasses import dataclass, field, fields
from pathlib import Path

import numpy as np
import shapely
import trimesh
import yaml
from manifold3d import CrossSection, FillRule, Manifold
from shapely import affinity
from shapely.geometry import MultiPolygon, Point, Polygon
from shapely.ops import nearest_points, unary_union

from .model import Drill
from .shapes import Board2D, as_multipolygon, drill_shape

GRID = 0.001        # mm: final 2D shapes are snapped to this grid (far below print resolution)
CLOSE_EPS = 0.002   # mm: grow-then-shrink distance that closes single-point touches
OPS = ("recess", "pocket", "through")
ALIGNMENT_KEYS = {"diameter": 3.0, "positions": "auto", "clearance": 3.0}


class RecipeError(ValueError):
    pass


@dataclass
class Recipe:
    """Built-in defaults are a plain conversion; params/3dpcb.yaml is the fabrication preset."""
    copper_layer: str = "F.Cu"
    base_thickness: float = 2.0         # mm of plastic under the copper
    copper_raise: float = 0.6           # mm the copper stands above the base
    arc_chord_mm: float = 0.02          # max error when approximating curves
    include_zones: bool = True
    include_copper_graphics: bool = True
    min_drill: float = 1.0              # mm; CLAUDE.md: holes ≥ 1 mm
    small_drill: str = "keep"           # enlarge | skip | keep (drills narrower than min_drill)
    alignment_holes: dict = field(default_factory=dict)   # {} = none; else diameter, positions, clearance
    extra_layers: dict = field(default_factory=dict)      # {"User.1": {"op": "recess", "depth": 1.5}}

    def validate(self):
        for name in ("base_thickness", "copper_raise", "arc_chord_mm", "min_drill"):
            if getattr(self, name) <= 0:
                raise RecipeError(f"{name} must be > 0 (got {getattr(self, name)})")
        if self.small_drill not in ("enlarge", "skip", "keep"):
            raise RecipeError(f"small_drill must be enlarge, skip or keep (got {self.small_drill!r})")
        if self.alignment_holes:
            unknown = sorted(set(self.alignment_holes) - set(ALIGNMENT_KEYS))
            if unknown:
                raise RecipeError(f"alignment_holes: unknown key(s) {unknown}; known: {sorted(ALIGNMENT_KEYS)}")
            a = {**ALIGNMENT_KEYS, **self.alignment_holes}
            if a["diameter"] <= 0 or a["clearance"] < 0:
                raise RecipeError("alignment_holes: diameter must be > 0 and clearance ≥ 0")
            pos = a["positions"]
            if pos != "auto" and not (isinstance(pos, list) and all(isinstance(p, list) and len(p) == 2 for p in pos)):
                raise RecipeError("alignment_holes.positions must be 'auto' or a list of [x, y] (KiCad mm)")
            self.alignment_holes = a
        for layer, spec in self.extra_layers.items():
            if not isinstance(spec, dict) or spec.get("op") not in OPS:
                raise RecipeError(f"extra_layers.{layer}: op must be one of {', '.join(OPS)}")
            if spec["op"] != "through":
                depth = spec.get("depth")
                if not isinstance(depth, (int, float)) or not 0 < depth < self.base_thickness:
                    raise RecipeError(f"extra_layers.{layer}: {spec['op']} needs 0 < depth < base_thickness "
                                      f"({self.base_thickness}); use op: through to cut all the way")


def load_recipe(path: str | Path | None) -> Recipe:
    if path is None:
        r = Recipe()
    else:
        data = yaml.safe_load(Path(path).read_text()) or {}
        known = {f.name for f in fields(Recipe)}
        unknown = sorted(set(data) - known)
        if unknown:
            raise RecipeError(f"{path}: unknown recipe key(s) {unknown}; known: {sorted(known)}")
        r = Recipe(**data)
    r.validate()
    return r


# ---- phase 4, 2D side: drills and alignment holes ------------------------------------------------

def _drill_policy(drills: list[Drill], recipe: Recipe) -> tuple[list[Drill], dict]:
    kept, enlarged, skipped = [], 0, 0
    for d in drills:
        if min(d.w, d.h) >= recipe.min_drill - 1e-9 or recipe.small_drill == "keep":
            kept.append(d)
        elif recipe.small_drill == "enlarge":
            kept.append(dataclasses.replace(d, w=max(d.w, recipe.min_drill), h=max(d.h, recipe.min_drill)))
            enlarged += 1
        else:
            skipped += 1
    return kept, {"enlarged": enlarged, "skipped": skipped}


def _alignment(b: Board2D, recipe: Recipe, holes, copper) -> tuple[list[tuple[float, float, float]], list[str]]:
    a = recipe.alignment_holes
    r = a["diameter"] / 2
    keep_clear = a["clearance"] + r + 0.01          # small margin: buffered circles are polygons, slightly inside
    blocked = unary_union([copper, holes] + [b.user_layers[k] for k in recipe.extra_layers if k in b.user_layers])
    room = b.outline.buffer(-keep_clear, quad_segs=32).difference(blocked.buffer(keep_clear, quad_segs=32))
    if a["positions"] != "auto":
        placed, warnings = [], []
        for x, y in a["positions"]:
            if room.contains(Point(x, y)):
                placed.append((float(x), float(y), a["diameter"]))
            else:
                warnings.append(f"alignment hole at ({x}, {y}) is closer than {a['clearance']} mm to copper, a hole "
                                f"or the edge; skipped")
        return placed, warnings
    if room.is_empty:
        return [], [f"no room for Ø{a['diameter']} alignment holes {a['clearance']} mm clear of copper, holes and "
                    f"edge (copper covers the board?); set alignment_holes.positions by hand"]
    x0, y0, x1, y1 = b.outline.bounds
    pairs = []
    for corners in (((x0, y0), (x1, y1)), ((x1, y0), (x0, y1))):   # both diagonals; pins far apart lock rotation
        pts = [nearest_points(room, Point(c))[0] for c in corners]
        pairs.append((pts[0].distance(pts[1]), pts))
    placed = [(round(p.x, 3), round(p.y, 3), a["diameter"]) for p in max(pairs, key=lambda t: t[0])[1]]
    warnings = []
    if Point(placed[0][:2]).distance(Point(placed[1][:2])) < 0.5 * Point(x0, y0).distance(Point(x1, y1)):
        warnings.append("alignment holes ended up close together (little free space); check them in preview.png")
    return placed, warnings


def prepare(b: Board2D, recipe: Recipe) -> tuple[Board2D, dict]:
    """Apply the 2D recipe extras. Returns the adjusted board and what changed (for the report)."""
    effects: dict = {"drills_enlarged": 0, "drills_skipped": 0, "alignment_holes": []}
    warnings = list(b.warnings)
    drills, counts = _drill_policy(b.drills, recipe)
    effects["drills_enlarged"], effects["drills_skipped"] = counts["enlarged"], counts["skipped"]
    if counts["enlarged"]:
        warnings.append(f"{counts['enlarged']} drill(s) narrower than {recipe.min_drill} mm enlarged to {recipe.min_drill} mm "
                        f"(copper rings smaller than the new hole disappear)")
    if counts["skipped"]:
        warnings.append(f"{counts['skipped']} drill(s) narrower than {recipe.min_drill} mm skipped (no hole)")
    changed = bool(counts["enlarged"] or counts["skipped"])
    holes = as_multipolygon(unary_union([drill_shape(d, recipe.arc_chord_mm) for d in drills])) if changed else b.holes

    merged = b.merged
    if changed:
        merged = {layer: as_multipolygon(unary_union([f.geom for f in feats]).difference(holes).intersection(b.outline))
                  for layer, feats in b.copper.items()}
    alignment = []
    if recipe.alignment_holes:
        alignment, more = _alignment(b, recipe, holes, merged.get(recipe.copper_layer, MultiPolygon()))
        warnings += more
        if alignment:
            pins = unary_union([Point(x, y).buffer(d / 2, quad_segs=32) for x, y, d in alignment])
            holes = as_multipolygon(unary_union([holes, pins]))
    effects["alignment_holes"] = [list(a) for a in alignment]
    return dataclasses.replace(b, drills=drills, holes=holes, merged=merged, alignment=alignment,
                               warnings=warnings), effects


# ---- 3D -------------------------------------------------------------------------------------------

@dataclass
class Build:
    mesh: trimesh.Trimesh             # the printable board, Y flipped (top view = KiCad view)
    solid: Manifold
    base_area: float                  # mm², outline minus drills
    copper_area: float                # mm², merged copper of the chosen layer
    warnings: list[str]
    extra_layers: list[dict] = field(default_factory=list)   # what each extra-layer op removed


def flip_y(geom):
    return affinity.scale(geom, xfact=1, yfact=-1, origin=(0, 0))


def regularize(geom):
    """Snap to GRID and close pinch points; changes areas by well under 0.01 %."""
    closed = geom.buffer(CLOSE_EPS, join_style="mitre").buffer(-CLOSE_EPS, join_style="mitre")
    return shapely.set_precision(closed, GRID)


def inside(geom, base):
    """`geom` clipped to stay at least GRID inside `base`, with single-point touches opened up."""
    # overlays on a grid can leave stray lines/points; keep only the polygons at each step
    clipped = as_multipolygon(shapely.intersection(regularize(geom), base.buffer(-GRID, join_style="mitre"), grid_size=GRID))
    opened = as_multipolygon(clipped.buffer(-CLOSE_EPS, join_style="mitre").buffer(CLOSE_EPS, join_style="mitre"))
    return as_multipolygon(shapely.intersection(opened, clipped, grid_size=GRID))


def cross_section(geom) -> CrossSection:
    rings = []
    for p in as_multipolygon(geom).geoms:
        rings.append(list(p.exterior.coords)[:-1])
        rings += [list(r.coords)[:-1] for r in p.interiors]
    return CrossSection(rings, FillRule.EvenOdd)


def to_trimesh(m: Manifold) -> trimesh.Trimesh:
    mesh = m.to_mesh()
    return trimesh.Trimesh(np.asarray(mesh.vert_properties)[:, :3], np.asarray(mesh.tri_verts), process=False)


def build(b: Board2D, recipe: Recipe) -> Build:
    if recipe.copper_layer not in b.merged:
        raise RecipeError(f"{recipe.copper_layer} is not a copper layer of this board ({', '.join(b.merged)})")
    warnings = []
    others = [layer for layer, g in b.merged.items() if layer != recipe.copper_layer and not g.is_empty]
    if others:
        warnings.append(f"copper on {', '.join(others)} is ignored (single-sided: only {recipe.copper_layer} is raised)")

    base_2d = regularize(flip_y(b.outline.difference(b.holes)))
    copper_2d = inside(flip_y(b.merged[recipe.copper_layer]), base_2d)
    solid = cross_section(base_2d).extrude(recipe.base_thickness)
    if not copper_2d.is_empty:
        solid = solid + cross_section(copper_2d).extrude(recipe.copper_raise).translate((0, 0, recipe.base_thickness))

    top = recipe.base_thickness + recipe.copper_raise
    ops = []
    for layer, spec in recipe.extra_layers.items():
        region = b.user_layers.get(layer)
        if region is None or region.is_empty:
            warnings.append(f"extra_layers.{layer}: the board has no shapes on {layer}; nothing cut")
            continue
        area_2d = inside(flip_y(region.intersection(b.outline)), base_2d)
        z0 = 0.0 if spec["op"] == "through" else recipe.base_thickness - spec["depth"]
        before = solid.volume()
        solid = solid - cross_section(area_2d).extrude(top - z0 + 1.0).translate((0, 0, z0))
        ops.append({"layer": layer, "op": spec["op"], "depth": round(recipe.base_thickness - z0, 4),
                    "area_mm2": round(area_2d.area, 3), "removed_mm3": round(before - solid.volume(), 3)})
    return Build(to_trimesh(solid), solid, base_2d.area, copper_2d.area, warnings, ops)


def section(bld: Build, z: float) -> MultiPolygon:
    """Horizontal slice of the solid at height z, in the 3D (Y-flipped) frame."""
    polys = [Polygon(r) for r in bld.solid.slice(z).to_polygons() if len(r) >= 3]
    # rings come as outer boundaries and holes; even-odd rebuild via symmetric difference
    out = MultiPolygon()
    for p in polys:
        out = out.symmetric_difference(p.buffer(0))
    return as_multipolygon(out)
