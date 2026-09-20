"""Where boards and conversion results live.

Local disk today. Everything is addressed by a content hash, so swapping in S3/R2
later means implementing the same four methods and changing one line in main.py.
"""
import hashlib
import json
import os
import zipfile
from pathlib import Path

ROOT = Path(os.environ.get("KICAD2CAD_STORAGE", "/tmp/kicad2cad-web")).resolve()


def digest(data: bytes | str) -> str:
    raw = data.encode() if isinstance(data, str) else data
    return hashlib.sha256(raw).hexdigest()[:16]


def canonical(obj) -> str:
    """Stable text for a recipe, so the same settings always hash the same."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


class Storage:
    def __init__(self, root: Path = ROOT):
        self.root = root
        (self.root / "boards").mkdir(parents=True, exist_ok=True)
        (self.root / "jobs").mkdir(parents=True, exist_ok=True)

    # ---- boards ---------------------------------------------------------------
    def board_dir(self, board_id: str) -> Path:
        return self.root / "boards" / board_id

    def put_board(self, data: bytes, name: str) -> str:
        board_id = digest(data)
        d = self.board_dir(board_id)
        d.mkdir(parents=True, exist_ok=True)
        (d / "board.kicad_pcb").write_bytes(data)
        (d / "meta.json").write_text(canonical({"name": name, "bytes": len(data)}))
        return board_id

    def put_board_file(self, path: Path, name: str) -> str:
        return self.put_board(Path(path).read_bytes(), name)

    def board_path(self, board_id: str) -> Path | None:
        p = self.board_dir(board_id) / "board.kicad_pcb"
        return p if p.exists() else None

    def board_meta(self, board_id: str) -> dict:
        p = self.board_dir(board_id) / "meta.json"
        return json.loads(p.read_text()) if p.exists() else {}

    # ---- jobs (one conversion = one content-addressed folder) -----------------
    def job_id(self, board_id: str, recipe: dict) -> str:
        return f"{board_id}-{digest(canonical(recipe))}"

    def job_dir(self, job_id: str) -> Path:
        return self.root / "jobs" / job_id

    def job_done(self, job_id: str) -> bool:
        return (self.job_dir(job_id) / "result.json").exists()

    def read_result(self, job_id: str) -> dict:
        return json.loads((self.job_dir(job_id) / "result.json").read_text())

    def write_result(self, job_id: str, result: dict):
        (self.job_dir(job_id) / "result.json").write_text(json.dumps(result, indent=1))

    def job_file(self, job_id: str, name: str) -> Path | None:
        """A file inside a job folder; refuses anything that escapes it."""
        base = self.job_dir(job_id).resolve()
        p = (base / name).resolve()
        return p if p.is_file() and p.is_relative_to(base) else None

    def bundle(self, job_id: str) -> Path:
        """Everything from one conversion, zipped. Built from an explicit file list so the
        zip can never end up inside itself."""
        d = self.job_dir(job_id)
        zip_path = d / "bundle.zip"
        if not zip_path.exists():
            members = sorted(p for p in d.rglob("*") if p.is_file() and p.name != "bundle.zip")
            tmp = d.parent / f"{job_id}.zip.tmp"
            with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
                for m in members:
                    z.write(m, m.relative_to(d).as_posix())
            tmp.replace(zip_path)
        return zip_path
