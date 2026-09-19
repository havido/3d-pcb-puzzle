"""Files written for people to look at. Phase 2: preview.png. Phase 3 adds 3MF/STL, the 1:1 PDF,
per-layer SVGs and report.json."""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import PathPatch  # noqa: E402
from matplotlib.path import Path as MplPath  # noqa: E402
from shapely.geometry import MultiPolygon, Polygon  # noqa: E402
from shapely.geometry.polygon import orient  # noqa: E402

from .shapes import Board2D  # noqa: E402

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
