# kicad2cad web

A browser front end for the converter: pick or drop a KiCad board, watch it become a printable board, change the settings, download the files.

```
web/app   React + three.js (Vite)      → Vercel
web/api   FastAPI around kicad2cad     → Render
```

## What the UI does
- **Boards:** three built-in samples (goose v3, test board, badge) or drag in any `.kicad_pcb`.
- **Live conversion:** the five steps (read → 2D shapes → settings → 3D → files) stream in as they finish, with counts and timings, ending in "KiCad → printable board in 0.4 s".
- **3D view:** orbit and zoom, copper and plate toggled separately, and a slider that slices through the board.
- **Settings:** every recipe value as a control, re-converting as you change it. Repeat settings come back from cache instantly.
- **Report:** size, copper area, volume, holes, whether the mesh is closed, and the warnings. Warnings with a position are clickable and the 3D view flies to them.
- **Downloads:** STL, 3MF, the 1:1 PDF, `report.json`, or everything as a zip.
- **Shareable:** the board and settings live in the URL.

## Built to grow
- **Job-shaped API.** `POST /api/convert` and `GET /api/jobs/{id}` already look like a queue, so a worker queue can slot in without touching the browser.
- **Content-addressed results.** Every job id is `sha256(board) + sha256(settings)`. Identical requests never convert twice, and the output is byte-identical.
- **Swappable storage.** `web/api/storage.py` is the only place that touches disk; replacing it with S3/R2 is four methods.
- **One schema.** `GET /api/recipe/schema` drives the UI controls. An AI layer later fills the same schema and calls the same endpoints, so it can't do anything the UI can't, and `Recipe.validate()` still checks every value. Add `/api/chat` with `OPENAI_API_KEY` set **on the server**; never ship a key to the browser.

## Run it locally
```bash
# API (from the repo root, with the venv active)
pip install -r requirements.txt && pip install -e .
uvicorn api.main:app --app-dir web --reload --port 8765

# UI (second terminal)
cd web/app && npm install && npm run dev      # http://localhost:5173
```
The UI talks to `http://localhost:8765` unless `VITE_API_BASE` says otherwise.

## Deploy the API to Render
1. Push this branch to GitHub.
2. Render → **New → Blueprint** → pick the repo → it reads `render.yaml` → **Apply**. (Manual instead: New → Web Service, Runtime **Python**, Build `pip install -r requirements.txt && pip install -e .`, Start `uvicorn api.main:app --app-dir web --host 0.0.0.0 --port $PORT --workers 1`, and add the env vars from `render.yaml`.)
3. Wait for the first build (a few minutes; it compiles nothing, but the wheels are large).
4. Check `https://YOUR-API.onrender.com/api/health` → `{"ok": true, ...}`.

## Deploy the UI to Vercel
1. Vercel → **Add New → Project** → pick the repo.
2. **Root Directory: `web/app`** (this is the one setting people miss). Framework "Vite" is detected.
3. Environment variable: `VITE_API_BASE = https://YOUR-API.onrender.com`
4. **Deploy**, then open the URL and convert the goose sample.
5. Back on Render, set `ALLOWED_ORIGINS` to your Vercel URL (e.g. `https://kicad2cad.vercel.app`) and redeploy, so it isn't open to every site.

Re-deploys: both platforms rebuild on push to the connected branch. A change to `VITE_API_BASE` needs a Vercel redeploy, because Vite bakes it into the bundle.

## Things to know before demo day
- **Free Render instances sleep after 15 minutes.** The first request then takes ~1 minute. Open the API URL a few minutes before demoing, or ping `/api/health` every 10 minutes during the event.
- **Memory:** idle 97 MB; goose 147 MB; the badge peaks at 329 MB of the free plan's 512 MB. Keep `--workers 1`. If it ever gets killed, drop the badge sample or move up a plan.
- **Storage is ephemeral** on free plans: the cache empties on redeploy, and the samples re-register at startup. Nothing else is lost.
- **Speed:** goose 0.4 s, badge ~3 s, cached results instant.
- **Alternatives:** Fly.io or Railway avoid the sleep; Cloud Run needs a container. Any of them runs the same start command.
