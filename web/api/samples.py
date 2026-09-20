"""Boards the demo can convert without an upload."""
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

SAMPLES = [
    dict(key="goose", name="Goose v3 (the demo board)", file=REPO / "goose" / "goose_landscape_v3.kicad_pcb",
         blurb="The board that docks on the badge: 3 mm traces, 158 × 133 mm."),
    dict(key="testboard", name="Test board", file=REPO / "tests" / "fixtures" / "testboard.kicad_pcb",
         blurb="Small board with every feature type: 50 × 40 mm, prints in 20 minutes."),
    dict(key="badge", name="Hacker badge (stress test)", file=REPO / "Archive 2" / "badge.kicad_pcb",
         blurb="A real 2-layer board: 634 tracks, 315 pads, 88 vias. Converts, but its 0.3 mm traces are too fine to print."),
]


def register_samples(store) -> list[dict]:
    out = []
    for s in SAMPLES:
        if not s["file"].exists():
            continue
        board_id = store.put_board_file(s["file"], s["file"].name)
        out.append({"key": s["key"], "name": s["name"], "blurb": s["blurb"],
                    "board_id": board_id, "filename": s["file"].name,
                    "bytes": s["file"].stat().st_size})
    return out
