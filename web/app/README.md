# kicad2cad UI

React + three.js front end for the converter. Deployment and the API live in [`../README.md`](../README.md).

## Run it
```bash
./web/dev.sh            # from the repo root: starts the API on :8765 and this app on :5173
```
Or in two terminals:
```bash
.venv/bin/uvicorn api.main:app --app-dir web --reload --port 8765
cd web/app && npm install && npm run dev
```
The app talks to `http://localhost:8765` unless `VITE_API_BASE` is set (see `.env.example`). Vite bakes that value in at build time, so changing it needs a rebuild.

## The files
| File | What's in it |
|---|---|
| `src/App.jsx` | All the state and the page layout: boards, settings, stages, result, warnings, downloads |
| `src/Viewer.jsx` | The 3D view: loads the STL, splits it into plate and copper, toggles, slice slider, camera |
| `src/api.js` | Every HTTP call. Nothing else should use `fetch` |
| `src/styles.css` | Plain CSS. Colours and spacing are tokens at the top (`:root`); no framework |

## How it flows
1. On load the app asks the API for `/api/recipe/schema` and `/api/samples`.
2. **The settings panel is generated from that schema**, so adding a control is a server-side change: add an entry to `RECIPE_FIELDS` in `web/api/convert.py` and it appears here. Don't hard-code fields in the UI.
3. Any change to the board or settings waits 350 ms, then opens an `EventSource` on `/api/convert/stream`. Each of the five steps arrives as a `stage` event, and the finished result arrives as `done`.
4. The result holds `job_id`, `stages`, `build` (volume, triangles, watertight, effects), `warnings`, `markers` (warnings that have a position), `outline`, and `files`. Download URLs come from `fileUrl(job_id, name)`.
5. The board and settings are written to the URL hash, so any result can be shared or reloaded.

## Worth knowing
- **Coordinates:** KiCad's Y axis points down; the 3D model flips it. A KiCad point `(x, y)` is `(x, -y)` in the viewer. That's why `Marker` and the camera use `-y`.
- **Splitting the mesh:** the STL is one solid. `splitByHeight` puts triangles that sit entirely at or above `base_thickness` in the copper group and the rest in the plate group, which is what makes the two toggles possible.
- **Slicing** needs `gl.localClippingEnabled = true` (set on the `Canvas`) plus `clippingPlanes` on each material.
- **React StrictMode** runs effects twice in dev, so you'll see two conversions on load. The second is served from cache; it isn't a bug.
- **Repeat settings are instant** (`cached: true` in the result). If you're testing a slow path, change a value to force real work.
- **The server sleeps** on Render's free plan: the first request after ~15 idle minutes takes about a minute.

## Before you push
```bash
cd web/app
npm run build        # CI runs this
npm run test:e2e     # CI runs this too: a real browser drives the app
```
`test:e2e` starts the API and the dev server if they aren't already up, then drives Chromium
through the Design tab: drawing a trace, switching tools mid-draw, double-click to finish,
selecting and moving, dragging a vertex, undo/redo, adding a hole, the live rules, opening the
goose and converting it to 3D. Add a case to `tests/design.spec.js` for anything you build;
`npm run test:e2e:headed` shows the browser while it runs, which is the quickest way to see
why something failed.

These caught the first round of bugs in this tab: a trace was added twice on Enter (a dispatch
inside a React state updater, which can run twice), a half-drawn trace stayed on screen after
switching tools, and an opened board landed off-camera.

Then click through by hand as well: pick each sample, drag in a `.kicad_pcb`, drag a slider,
toggle copper and plate, move the slice slider, click a warning, download an STL, reload the
page (the URL should restore your state).

## Good first tasks
1. **Busy state.** While a conversion runs, dim the viewer and show a spinner instead of the old board silently staying put.
2. **Cold-start message.** If the first request takes more than ~3 s, say "waking the server, this takes up to a minute" rather than leaving it blank.
3. **Top view tab.** Draw the warning markers over `preview.png` and let clicking one jump to the 3D view.
4. **Mobile layout.** The grid collapses under 1100 px but hasn't been tried on a phone.
5. **Reset view button** in the viewer, plus a keyboard shortcut.
6. **Show the equivalent command line** for the current settings, so people can reproduce a result locally.
