"""kicad2cad web API.

Endpoints are shaped as jobs and every result is content-addressed, so the same work
is never done twice and a queue or object storage can be slotted in later without the
browser noticing. The AI layer, when it arrives, calls these same endpoints.
"""
import asyncio
import json
import os
from functools import partial
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from . import convert as conv
from .samples import SAMPLES, register_samples
from .storage import Storage

MAX_UPLOAD = int(os.environ.get("MAX_UPLOAD_BYTES", 30_000_000))
ORIGINS = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
# Vercel gives every preview deployment its own URL, so allow a pattern as well as a list.
ORIGIN_REGEX = os.environ.get("ALLOWED_ORIGIN_REGEX") or None

app = FastAPI(title="kicad2cad", version="0.1.0",
              description="Turn a KiCad board into a 3D-printable 3DPCB board.")
app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_origin_regex=ORIGIN_REGEX,
                   allow_methods=["*"], allow_headers=["*"])
store = Storage()
samples = register_samples(store)


class ConvertIn(BaseModel):
    board_id: str
    settings: dict = Field(default_factory=dict)


@app.get("/api/health")
def health():
    return {"ok": True, "version": app.version, "samples": len(samples)}


@app.get("/api/recipe/schema")
def recipe_schema():
    """The settings the UI renders and an AI layer would fill in."""
    return {"fields": conv.RECIPE_FIELDS, "defaults": conv.DEFAULTS}


@app.get("/api/samples")
def list_samples():
    return samples


@app.post("/api/boards")
async def upload_board(file: UploadFile):
    if not file.filename.endswith(".kicad_pcb"):
        raise HTTPException(400, "please upload a .kicad_pcb file")
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, f"file is larger than {MAX_UPLOAD // 1_000_000} MB")
    if b"kicad_pcb" not in data[:200]:
        raise HTTPException(400, "that doesn't look like a KiCad board file")
    board_id = store.put_board(data, file.filename)
    return {"board_id": board_id, "name": file.filename, "bytes": len(data)}


def _convert(board_id: str, settings: dict, on_stage=None) -> dict:
    path = store.board_path(board_id)
    if path is None:
        raise HTTPException(404, "unknown board id; upload it again")
    try:
        recipe = conv.recipe_from(settings)            # validate before hashing
    except conv.RecipeError as e:
        raise HTTPException(400, str(e))
    job_id = store.job_id(board_id, {**conv.DEFAULTS, **settings})
    if store.job_done(job_id):
        result = store.read_result(job_id)
        result["cached"] = True
        return result
    try:
        result = conv.run(path, settings, store.job_dir(job_id), on_stage=on_stage)
    except conv.ParseError as e:
        raise HTTPException(422, f"could not read that board: {e}")
    except conv.RecipeError as e:
        raise HTTPException(400, str(e))
    result |= {"job_id": job_id, "board_id": board_id, "board_name": store.board_meta(board_id).get("name", ""),
               "cached": False}
    store.write_result(job_id, result)
    return result


@app.post("/api/convert")
def convert_board(body: ConvertIn):
    """Convert and return the whole result (used when replaying a cached job)."""
    return _convert(body.board_id, body.settings)


@app.get("/api/convert/stream")
async def convert_stream(board_id: str, settings: str = Query("{}")):
    """Same conversion, streamed stage by stage so the browser can show it happening."""
    try:
        values = json.loads(settings)
    except json.JSONDecodeError:
        raise HTTPException(400, "settings must be JSON")
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def on_stage(stage: dict):
        loop.call_soon_threadsafe(queue.put_nowait, ("stage", stage))

    async def worker():
        try:
            result = await asyncio.to_thread(partial(_convert, board_id, values, on_stage))
            await queue.put(("done", result))
        except HTTPException as e:
            await queue.put(("error", {"detail": e.detail}))
        except Exception as e:                                    # noqa: BLE001 - surfaced to the browser
            await queue.put(("error", {"detail": f"{type(e).__name__}: {e}"}))

    async def events():
        task = asyncio.create_task(worker())
        try:
            while True:
                kind, payload = await queue.get()
                yield f"event: {kind}\ndata: {json.dumps(payload)}\n\n"
                if kind in ("done", "error"):
                    return
        finally:
            task.cancel()

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/jobs/{job_id}")
def job(job_id: str):
    if not store.job_done(job_id):
        raise HTTPException(404, "unknown job")
    return store.read_result(job_id) | {"cached": True}


@app.get("/api/jobs/{job_id}/files/{name:path}")
def job_file(job_id: str, name: str):
    path = store.job_file(job_id, name)
    if path is None:
        raise HTTPException(404, "no such file in this job")
    return FileResponse(path, filename=Path(name).name)


@app.get("/api/jobs/{job_id}/bundle.zip")
def job_bundle(job_id: str):
    if not store.job_done(job_id):
        raise HTTPException(404, "unknown job")
    return FileResponse(store.bundle(job_id), filename="kicad2cad.zip")
