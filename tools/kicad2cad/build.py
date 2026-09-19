"""Phase 3: `Board2D` + recipe → 3D solids.

Everything is 2.5D: the base plate is the outline (minus drills) extruded to
`base_thickness`, and the copper is extruded `copper_raise` high and stacked on top.
KiCad's Y axis points down, so Y is flipped here, once: looking down on the printed
board you see what KiCad shows.

Mesh hygiene (found on the badge: its STL wasn't watertight once saved and reloaded):
- all final 2D shapes live on a 1 µm grid (GRID), so no two distinct points are closer
  than an STL's float32 coordinates can tell apart;
- shapes that touch at a single point ("pinch points", e.g. thermal-relief spokes) are
  closed with a CLOSE_EPS grow-and-shrink, turning each into a tiny neck;
- the copper sits on the base instead of starting at z = 0, so no two faces overlap.
"""
from dataclasses import dataclass, field, fields
from pathlib import Path

import numpy as np
import shapely
import trimesh
import yaml
from manifold3d import CrossSection, FillRule, Manifold
from shapely import affinity
from shapely.geometry import MultiPolygon, Polygon

from .shapes import Board2D, as_multipolygon


GRID = 0.001        # mm: final 2D shapes are snapped to this grid (far below print resolution)
CLOSE_EPS = 0.002   # mm: grow-then-shrink distance that closes single-point touches


class RecipeError(ValueError):
    pass


@dataclass
class Recipe:
    copper_layer: str = "F.Cu"
    base_thickness: float = 2.0         # mm of plastic under the copper
    copper_raise: float = 0.6           # mm the copper stands above the base
    arc_chord_mm: float = 0.02          # max error when approximating curves
    include_zones: bool = True
    include_copper_graphics: bool = True
    # Phase 4 (read and validated now, applied later; setting them warns until then):
    min_drill: float = 1.0
    small_drill: str = "keep"           # enlarge | skip | keep
    alignment_holes: dict = field(default_factory=dict)
    extra_layers: dict = field(default_factory=dict)

    def validate(self):
        for name in ("base_thickness", "copper_raise", "arc_chord_mm"):
            if getattr(self, name) <= 0:
                raise RecipeError(f"{name} must be > 0 (got {getattr(self, name)})")
        if self.small_drill not in ("enlarge", "skip", "keep"):
            raise RecipeError(f"small_drill must be enlarge, skip or keep (got {self.small_drill!r})")

    def pending_warnings(self) -> list[str]:
        out = []
        if self.small_drill != "keep":
            out.append(f"recipe small_drill={self.small_drill} is not applied yet (phase 4); drills are kept as drawn")
        if self.alignment_holes:
            out.append("recipe alignment_holes are not applied yet (phase 4)")
        if self.extra_layers:
            out.append(f"recipe extra_layers {sorted(self.extra_layers)} are not applied yet (phase 4)")
        return out


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


@dataclass
class Build:
    mesh: trimesh.Trimesh             # the printable board, Y flipped (top view = KiCad view)
    solid: Manifold
    base_area: float                  # mm², outline minus drills
    copper_area: float                # mm², merged copper of the chosen layer
    warnings: list[str]


def flip_y(geom):
    return affinity.scale(geom, xfact=1, yfact=-1, origin=(0, 0))


def regularize(geom):
    """Snap to GRID and close pinch points; changes areas by well under 0.01 %."""
    closed = geom.buffer(CLOSE_EPS, join_style="mitre").buffer(-CLOSE_EPS, join_style="mitre")
    return shapely.set_precision(closed, GRID)


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
    warnings = recipe.pending_warnings()
    others = [layer for layer, g in b.merged.items() if layer != recipe.copper_layer and not g.is_empty]
    if others:
        warnings.append(f"copper on {', '.join(others)} is ignored (single-sided: only {recipe.copper_layer} is raised)")

    base_2d = regularize(flip_y(b.outline.difference(b.holes)))
    copper_2d = shapely.intersection(regularize(flip_y(b.merged[recipe.copper_layer])), base_2d, grid_size=GRID)
    solid = cross_section(base_2d).extrude(recipe.base_thickness)
    if not copper_2d.is_empty:
        solid = solid + cross_section(copper_2d).extrude(recipe.copper_raise).translate((0, 0, recipe.base_thickness))
    return Build(to_trimesh(solid), solid, base_2d.area, copper_2d.area, warnings)


def section(bld: Build, z: float) -> MultiPolygon:
    """Horizontal slice of the solid at height z, in the 3D (Y-flipped) frame."""
    polys = [Polygon(r) for r in bld.solid.slice(z).to_polygons() if len(r) >= 3]
    # rings come as outer boundaries and holes; even-odd rebuild via symmetric difference
    out = MultiPolygon()
    for p in polys:
        out = out.symmetric_difference(p.buffer(0))
    return as_multipolygon(out)
