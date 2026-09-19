"""Small geometry helpers in KiCad coordinates (mm, Y pointing down, angles in degrees)."""
import math

Point = tuple[float, float]


def place(fx: float, fy: float, frot: float, px: float, py: float) -> Point:
    """Position of a footprint child: (px, py) is in the footprint's own, unrotated frame.

    Verified on the badge board: with this sign, pads of rotated footprints land
    exactly on their tracks' end points.
    """
    a = math.radians(frot)
    c, s = math.cos(a), math.sin(a)
    return fx + px * c + py * s, fy - px * s + py * c


def _step(r: float, max_err: float) -> float:
    """Largest angle step whose chord stays within `max_err` of the true circle."""
    if r <= max_err:
        return math.pi / 2
    return 2 * math.acos(1 - max_err / r)


def circle_through(p1: Point, p2: Point, p3: Point) -> tuple[float, float, float] | None:
    """Centre and radius of the circle through three points, or None if they're collinear."""
    (ax, ay), (bx, by), (cx, cy) = p1, p2, p3
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-12:
        return None
    a2, b2, c2 = ax * ax + ay * ay, bx * bx + by * by, cx * cx + cy * cy
    ux = (a2 * (by - cy) + b2 * (cy - ay) + c2 * (ay - by)) / d
    uy = (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / d
    return ux, uy, math.hypot(ax - ux, ay - uy)


def arc_points(start: Point, mid: Point, end: Point, max_err: float) -> list[Point]:
    """Points along the arc from `start` through `mid` to `end`; the end points are exact."""
    circle = circle_through(start, mid, end)
    if circle is None:
        return [start, end]
    cx, cy, r = circle
    a0 = math.atan2(start[1] - cy, start[0] - cx)
    am = math.atan2(mid[1] - cy, mid[0] - cx)
    a1 = math.atan2(end[1] - cy, end[0] - cx)
    sweep_end = (a1 - a0) % (2 * math.pi)
    sweep_mid = (am - a0) % (2 * math.pi)
    total = sweep_end if sweep_mid <= sweep_end else sweep_end - 2 * math.pi
    n = max(2, math.ceil(abs(total) / _step(r, max_err)))
    pts = [(cx + r * math.cos(a0 + total * i / n), cy + r * math.sin(a0 + total * i / n)) for i in range(n + 1)]
    pts[0], pts[-1] = start, end
    return pts


def circle_points(cx: float, cy: float, r: float, max_err: float) -> list[Point]:
    """Closed ring (first point repeated at the end) approximating a circle."""
    n = max(8, math.ceil(2 * math.pi / _step(r, max_err)))
    pts = [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)]
    return pts + [pts[0]]
