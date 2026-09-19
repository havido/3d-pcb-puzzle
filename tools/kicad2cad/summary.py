"""Counts and sizes of a parsed board: what `kicad2cad FILE --summary` prints."""
from collections import Counter

from .model import KicadBoard


def summarize(b: KicadBoard) -> dict:
    x0, y0, x1, y1 = b.outline.bounds
    holes = []
    for ring in b.outline.interiors:
        hx0, hy0, hx1, hy1 = ring.bounds
        holes.append({"center": [round((hx0 + hx1) / 2, 3), round((hy0 + hy1) / 2, 3)],
                      "size": [round(hx1 - hx0, 3), round(hy1 - hy0, 3)]})
    per_layer = {}
    for layer in b.copper_layers:
        per_layer[layer] = {
            "segments": sum(1 for t in b.tracks if t.layer == layer and t.mid is None),
            "arcs": sum(1 for t in b.tracks if t.layer == layer and t.mid is not None),
            "pads": sum(1 for p in b.pads if layer in p.layers),
            "vias": sum(1 for v in b.vias if layer in v.layers),
            "zones": [{"net": z.net, "filled_polygons": len(z.polygons)} for z in b.zones if z.layer == layer],
            "graphics": dict(Counter(g.kind for g in b.graphics if g.layer == layer)),
        }
    return {
        "source": b.source,
        "sha256": b.sha256,
        "version": b.version,
        "generator_version": b.generator_version,
        "outline": {
            "bbox": [round(x0, 3), round(y0, 3), round(x1, 3), round(y1, 3)],
            "size_mm": [round(x1 - x0, 3), round(y1 - y0, 3)],
            "area_mm2": round(b.outline.area, 3),
            "holes": holes,
        },
        "copper": per_layer,
        "pad_shapes": dict(Counter(f"{p.kind}/{p.shape}" for p in b.pads)),
        "vias_by_size_drill": {f"{s}/{d}": n for (s, d), n in Counter((v.size, v.drill) for v in b.vias).items()},
        "drills": {"total": len(b.drills), "oval": sum(1 for d in b.drills if d.w != d.h),
                   "plated": sum(1 for d in b.drills if d.plated)},
        "keepouts_ignored": b.keepouts,
        "user_layers": {k: len(v) for k, v in b.user_layers.items()},
        "warnings": b.warnings,
    }


def format_summary(s: dict) -> str:
    o = s["outline"]
    lines = [
        f"{s['source']}  (format {s['version']}, KiCad {s['generator_version']})",
        f"outline   {o['size_mm'][0]} x {o['size_mm'][1]} mm, bbox {o['bbox']}, {len(o['holes'])} interior cut-out(s)",
    ]
    for h in o["holes"]:
        lines.append(f"          cut-out at {h['center']} size {h['size']}")
    for layer, c in s["copper"].items():
        g = ", ".join(f"{k} {v}" for k, v in c["graphics"].items()) or "none"
        z = ", ".join(f"{zz['net']} ({zz['filled_polygons']} filled)" for zz in c["zones"]) or "none"
        lines.append(f"{layer:<9} {c['segments']} segments, {c['arcs']} arcs, {c['pads']} pads, "
                     f"{c['vias']} vias | zones: {z} | graphics: {g}")
    lines.append("pads      " + ", ".join(f"{k} {v}" for k, v in sorted(s["pad_shapes"].items())))
    lines.append("vias      " + (", ".join(f"{k} x{v}" for k, v in s["vias_by_size_drill"].items()) or "none"))
    d = s["drills"]
    lines.append(f"drills    {d['total']} ({d['plated']} plated, {d['oval']} oval); keep-outs ignored: {s['keepouts_ignored']}")
    if s["user_layers"]:
        lines.append("user      " + ", ".join(f"{k} {v} shape(s)" for k, v in s["user_layers"].items()))
    lines.append(f"warnings  {len(s['warnings'])}")
    lines += [f"  ! {w}" for w in s["warnings"]]
    return "\n".join(lines)
