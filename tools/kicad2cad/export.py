"""Everything kicad2cad writes: preview.png, board.stl/.3mf, plot_1to1.pdf, layers/*.svg, report.json."""
import dataclasses
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import PathPatch  # noqa: E402
from matplotlib.path import Path as MplPath  # noqa: E402
from shapely.geometry import MultiPolygon, Polygon  # noqa: E402
from shapely.geometry.polygon import orient  # noqa: E402

from .shapes import Board2D  # noqa: E402
from .shapes import as_multipolygon as as_mp  # noqa: E402

COLORS = {"board": "#e6e2d8", "edge": "#5b5b5b", "copper": "#d9822b", "user": "#3b6fb6", "marker": "#d62728"}


def _path(geom) -> MplPath | None:
    """A matplotlib path for a (Multi)Polygon, with holes drawn as holes."""
    polys = [geom] if isinstance(geom, Polygon) else list(getattr(geom, "geoms", []))
    verts, codes = [], []
    for p in polys:
        if p.is_empty:
            continue
        p = orient(p, 1.0)                        # exterior CCW, holes CW → holes render empty
        for ring in [p.exterior, *p.interiors]:
            pts = list(ring.coords)
            verts += pts
            codes += [MplPath.MOVETO] + [MplPath.LINETO] * (len(pts) - 2) + [MplPath.CLOSEPOLY]
    return MplPath(verts, codes) if verts else None


def _draw(ax, geom, **style):
    path = _path(geom)
    if path is not None:
        ax.add_patch(PathPatch(path, **style))


def write_preview(b: Board2D, path: str | Path, layer: str = "F.Cu", title: str | None = None) -> Path:
    """Top view as seen in KiCad (Y down): board, copper of `layer`, holes, user layers, warnings."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    x0, y0, x1, y1 = b.outline.bounds
    w, h = x1 - x0, y1 - y0
    pad = max(w, h) * 0.06
    scale = 8 / max(w, h)                                     # longest side ≈ 8 inches
    fig = plt.figure(figsize=((w + 2 * pad) * scale, (h + 2 * pad) * scale + 0.9))
    ax = fig.add_axes((0, 0, 1, (h + 2 * pad) * scale / ((h + 2 * pad) * scale + 0.9)))
    ax.set_xlim(x0 - pad, x1 + pad)
    ax.set_ylim(y1 + pad, y0 - pad)                           # Y down, exactly like KiCad
    ax.set_aspect("equal")
    ax.axis("off")

    _draw(ax, b.outline, facecolor=COLORS["board"], edgecolor=COLORS["edge"], linewidth=0.8)
    for name, geom in b.user_layers.items():
        _draw(ax, geom, facecolor="none", edgecolor=COLORS["user"], linewidth=0.8, hatch="///")
    _draw(ax, b.merged.get(layer, MultiPolygon()), facecolor=COLORS["copper"], edgecolor="none")
    _draw(ax, b.holes, facecolor="white", edgecolor=COLORS["edge"], linewidth=0.3)
    for i, (mx, my, _) in enumerate(b.markers, 1):
        ax.add_patch(plt.Circle((mx, my), max(1.5, max(w, h) * 0.015), fill=False, color=COLORS["marker"], linewidth=1.5))
        ax.annotate(str(i), (mx, my), xytext=(4, -4), textcoords="offset points", color=COLORS["marker"], fontsize=9, weight="bold")

    bar = 10 if max(w, h) < 150 else 20                        # scale bar, bottom-left
    bx, by = x0, y1 + pad * 0.55
    ax.plot([bx, bx + bar], [by, by], color="black", linewidth=2)
    ax.annotate(f"{bar} mm", (bx + bar / 2, by), xytext=(0, 3), textcoords="offset points", ha="center", fontsize=8)

    area = b.merged.get(layer, MultiPolygon()).area
    lines = [f"TOP VIEW (as in KiCad) · {title or Path(b.source).name} · {w:.1f} × {h:.1f} mm",
             f"{layer} copper {area:.0f} mm² · {len(b.drills)} holes · user layers: {', '.join(b.user_layers) or 'none'}"]
    lines += [f"({i}) {msg[:110]}" for i, (_, _, msg) in enumerate(b.markers, 1)][:4]
    unlocated = len(b.warnings) - len(b.markers)
    if unlocated > 0:
        lines.append(f"+ {unlocated} more warning(s) without a position, see the summary")
    fig.text(0.01, 0.995, "\n".join(lines), va="top", ha="left", fontsize=8, family="monospace")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


# ---- phase 3: 3D files, true-scale PDF, SVG layers, report -----------------------------------------

def write_meshes(mesh, out: Path) -> dict[str, Path]:
    """board.stl (binary, byte-for-byte repeatable) and board.3mf (mm units; the zip holds timestamps)."""
    out.mkdir(parents=True, exist_ok=True)
    stl, tmf = out / "board.stl", out / "board.3mf"
    stl.write_bytes(mesh.export(file_type="stl"))
    mesh.export(str(tmf), file_type="3mf")
    return {"stl": stl, "3mf": tmf}


def write_plot_1to1(b: Board2D, path: str | Path, layer: str = "F.Cu") -> Path:
    """A PDF whose page is exactly the board size (+ margins): printed at 100 %, 1 mm on paper = 1 mm."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    x0, y0, x1, y1 = b.outline.bounds
    w, h = x1 - x0, y1 - y0
    margin, footer, min_page_w = 10.0, 22.0, 120.0               # mm; wide enough for the footer text
    page_w, page_h = max(w + 2 * margin, min_page_w), h + 2 * margin + footer
    fig = plt.figure(figsize=(page_w / 25.4, page_h / 25.4))
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(x0 - margin, x0 - margin + page_w)
    ax.set_ylim(y1 + margin + footer, y0 - margin)                # Y down, as in KiCad; 1 data unit = 1 mm
    ax.axis("off")
    _draw(ax, b.outline, facecolor="none", edgecolor="black", linewidth=0.4)
    _draw(ax, b.merged.get(layer, MultiPolygon()), facecolor="#bbbbbb", edgecolor="black", linewidth=0.2)
    _draw(ax, b.holes, facecolor="white", edgecolor="black", linewidth=0.2)
    bar = 50.0 if w >= 50 else 20.0
    by = y1 + margin + 4
    ax.plot([x0, x0 + bar], [by, by], color="black", linewidth=1.5, solid_capstyle="butt")
    for x in (x0, x0 + bar):
        ax.plot([x, x], [by - 1.5, by + 1.5], color="black", linewidth=0.8)
    notes = [f"Print at 100 % (Actual size, not Fit to page). This bar must measure {bar:.0f} mm.",
             f"TOP VIEW (as in KiCad) · {Path(b.source).name}",
             f"Board {w:.1f} × {h:.1f} mm"]
    for i, line in enumerate(notes):
        ax.text(x0, by + 4 + 3.2 * i, line, fontsize=6, va="top")
    fig.savefig(path)
    plt.close(fig)
    return path


def _svg_path(geom) -> str:
    parts = []
    for p in (as_mp(geom)).geoms:
        for ring in [p.exterior, *p.interiors]:
            pts = list(ring.coords)
            parts.append("M" + " L".join(f"{x:.4f},{y:.4f}" for x, y in pts[:-1]) + " Z")
    return " ".join(parts)


def write_svgs(b: Board2D, out: Path, layer: str = "F.Cu") -> list[Path]:
    """One SVG per layer, in mm, KiCad orientation (Y down): outline, the copper layer, each user layer."""
    out.mkdir(parents=True, exist_ok=True)
    x0, y0, x1, y1 = b.outline.bounds
    w, h = x1 - x0, y1 - y0
    layers = {"outline": (b.outline, "#e6e2d8"), layer: (b.merged.get(layer, MultiPolygon()), COLORS["copper"])}
    layers.update({name: (g, COLORS["user"]) for name, g in b.user_layers.items()})
    written = []
    for name, (geom, color) in layers.items():
        f = out / f"{name}.svg"
        f.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.4f}mm" height="{h:.4f}mm" '
                     f'viewBox="{x0:.4f} {y0:.4f} {w:.4f} {h:.4f}">\n'
                     f'  <path fill="{color}" fill-rule="evenodd" d="{_svg_path(geom)}"/>\n</svg>\n')
        written.append(f)
    return written


def write_report(path: Path, summary: dict, recipe, bld, files: dict[str, Path], seconds: float) -> Path:
    m = bld.mesh
    report = dict(summary)
    report["build"] = {
        "recipe": dataclasses.asdict(recipe),
        "base_area_mm2": round(bld.base_area, 3),
        "copper_area_mm2": round(bld.copper_area, 3),
        "volume_mm3": round(float(m.volume), 3),
        "volume_formula_mm3": round(bld.base_area * recipe.base_thickness + bld.copper_area * recipe.copper_raise, 3),
        "bounds_mm": [[round(float(v), 4) for v in row] for row in m.bounds],
        "triangles": int(len(m.faces)),
        "watertight": bool(m.is_watertight),
        "is_volume": bool(m.is_volume),
        "files": {k: {"path": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for k, p in files.items()},
        "seconds": round(seconds, 2),
    }
    report["warnings"] = summary["warnings"] + bld.warnings
    path.write_text(json.dumps(report, indent=1) + "\n")
    return path
