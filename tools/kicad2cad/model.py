"""What the parser reads out of a .kicad_pcb, in KiCad coordinates (mm, Y down).

Phase 2 (`shapes.py`) turns these primitives into polygons and builds the
`Board2D` contract described in docs/kicad2cad-plan.md.
"""
from dataclasses import dataclass, field

from shapely.geometry import Polygon

from .geom import Point


@dataclass
class Track:
    layer: str
    net: str | None
    width: float
    start: Point
    end: Point
    mid: Point | None = None          # set for arcs (start -> mid -> end)


@dataclass
class Drill:
    x: float
    y: float
    w: float                          # w == h for round holes
    h: float
    angle: float                      # degrees
    plated: bool
    net: str | None


@dataclass
class Pad:
    ref: str | None                   # footprint reference, e.g. "SW2"
    number: str
    kind: str                         # smd | thru_hole | np_thru_hole | connect
    shape: str                        # circle | rect | roundrect | oval | trapezoid | custom
    x: float                          # board coordinates (footprint rotation applied)
    y: float
    angle: float                      # absolute pad angle as stored in the file
    fp_angle: float                   # the parent footprint's rotation
    w: float
    h: float
    rratio: float                     # roundrect corner ratio
    layers: list[str]                 # copper layers only, "*.Cu" expanded
    net: str | None
    drill: Drill | None


@dataclass
class Via:
    x: float
    y: float
    size: float
    drill: float
    layers: list[str]
    net: str | None


@dataclass
class Zone:
    layer: str
    net: str | None
    polygons: list[Polygon]           # the filled areas (or the outline, with a warning, if unfilled)


@dataclass
class Graphic:
    """A drawn shape (line, arc, circle, rect or polygon) on a copper or user layer."""
    kind: str
    layer: str
    points: list[Point]               # already in board coordinates; arcs/circles sampled
    width: float                      # stroke width
    filled: bool
    closed: bool


@dataclass
class KicadBoard:
    source: str
    sha256: str
    version: int
    generator_version: str | None
    copper_layers: list[str]
    outline: Polygon                  # interior cut-outs are its holes
    tracks: list[Track] = field(default_factory=list)
    pads: list[Pad] = field(default_factory=list)
    vias: list[Via] = field(default_factory=list)
    zones: list[Zone] = field(default_factory=list)
    graphics: list[Graphic] = field(default_factory=list)          # on copper layers
    user_layers: dict[str, list[Graphic]] = field(default_factory=dict)
    drills: list[Drill] = field(default_factory=list)
    keepouts: int = 0
    warnings: list[str] = field(default_factory=list)
