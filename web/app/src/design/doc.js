// The document (see docs/whiteboard-plan.md §3), the ops that edit it, and an
// undo/redo reducer. Every op is a pure function: (doc, ...args) -> doc.
// Nothing here mutates its arguments, so old snapshots kept for undo stay valid.
//
// This file also carries the small geometry helpers (distance, point-in-polygon,
// snapping) shared by rules.js (fabrication checks) and Canvas.jsx (hit-testing,
// drag previews) — there is no separate geometry module, to keep the file count
// matching the plan.

let idCounter = 0
export function uid(prefix = 'o') {
  idCounter += 1
  return `${prefix}_${idCounter}_${Math.random().toString(36).slice(2, 8)}`
}

// ---------------------------------------------------------------- geometry --

export function dist(p, q) {
  return Math.hypot(p[0] - q[0], p[1] - q[1])
}

export function midpoint(points) {
  const n = points.length
  let sx = 0, sy = 0
  for (const p of points) { sx += p[0]; sy += p[1] }
  return [sx / n, sy / n]
}

export function nearestPointOnSegment(p, a, b) {
  const abx = b[0] - a[0], aby = b[1] - a[1]
  const len2 = abx * abx + aby * aby
  let t = len2 === 0 ? 0 : ((p[0] - a[0]) * abx + (p[1] - a[1]) * aby) / len2
  t = Math.max(0, Math.min(1, t))
  return { point: [a[0] + abx * t, a[1] + aby * t], t }
}

export function distToSegment(p, a, b) {
  return dist(p, nearestPointOnSegment(p, a, b).point)
}

function orient(a, b, c) {
  return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
}
function onSegment(a, b, p) {
  const eps = 1e-9
  return Math.min(a[0], b[0]) - eps <= p[0] && p[0] <= Math.max(a[0], b[0]) + eps &&
         Math.min(a[1], b[1]) - eps <= p[1] && p[1] <= Math.max(a[1], b[1]) + eps
}

export function segmentsIntersect(a1, a2, b1, b2) {
  const d1 = orient(b1, b2, a1), d2 = orient(b1, b2, a2)
  const d3 = orient(a1, a2, b1), d4 = orient(a1, a2, b2)
  if (((d1 > 0 && d2 < 0) || (d1 < 0 && d2 > 0)) && ((d3 > 0 && d4 < 0) || (d3 < 0 && d4 > 0))) return true
  if (d1 === 0 && onSegment(b1, b2, a1)) return true
  if (d2 === 0 && onSegment(b1, b2, a2)) return true
  if (d3 === 0 && onSegment(a1, a2, b1)) return true
  if (d4 === 0 && onSegment(a1, a2, b2)) return true
  return false
}

// Approximate (but exact for the non-crossing case, which is nearly all of them):
// zero if the segments cross, otherwise the smaller of the four endpoint-to-segment distances.
export function segmentDistance(a1, a2, b1, b2) {
  if (segmentsIntersect(a1, a2, b1, b2)) return 0
  return Math.min(
    distToSegment(a1, b1, b2),
    distToSegment(a2, b1, b2),
    distToSegment(b1, a1, a2),
    distToSegment(b2, a1, a2),
  )
}

export function pointInPolygon([x, y], poly) {
  let inside = false
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i], [xj, yj] = poly[j]
    const crosses = (yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi
    if (crosses) inside = !inside
  }
  return inside
}

export function distToPolygon(p, poly) {
  let min = Infinity
  for (let i = 0; i < poly.length; i++) {
    const d = distToSegment(p, poly[i], poly[(i + 1) % poly.length])
    if (d < min) min = d
  }
  return min
}

export function polygonBounds(points) {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
  for (const [x, y] of points) {
    if (x < minX) minX = x
    if (x > maxX) maxX = x
    if (y < minY) minY = y
    if (y > maxY) maxY = y
  }
  return { minX, minY, maxX, maxY }
}

// ------------------------------------------------------------------ snapping --

export function snapToGrid([x, y], grid = 1) {
  return [Math.round(x / grid) * grid, Math.round(y / grid) * grid]
}

// Snaps the direction from `origin` to `point` to the nearest 45 degree step,
// keeping the drawn length. Used while drafting a trace/outline segment.
export function snapAngle(origin, point, stepDeg = 45) {
  const dx = point[0] - origin[0], dy = point[1] - origin[1]
  const length = Math.hypot(dx, dy)
  if (length < 1e-9) return [origin[0], origin[1]]
  const step = (stepDeg * Math.PI) / 180
  const angle = Math.round(Math.atan2(dy, dx) / step) * step
  return [origin[0] + Math.cos(angle) * length, origin[1] + Math.sin(angle) * length]
}

// ------------------------------------------------------------- outline presets --

function rectanglePoints(w, h) {
  return [[0, 0], [w, 0], [w, h], [0, h]]
}

function roundedRectanglePoints(w, h, r, segsPerCorner = 6) {
  r = Math.min(r ?? Math.min(w, h) * 0.12, w / 2, h / 2)
  const corners = [
    { cx: w - r, cy: r, start: -90 },   // top-right
    { cx: w - r, cy: h - r, start: 0 }, // bottom-right
    { cx: r, cy: h - r, start: 90 },    // bottom-left
    { cx: r, cy: r, start: 180 },       // top-left
  ]
  const pts = []
  for (const c of corners) {
    for (let i = 0; i <= segsPerCorner; i++) {
      const a = ((c.start + (i / segsPerCorner) * 90) * Math.PI) / 180
      pts.push([c.cx + Math.cos(a) * r, c.cy + Math.sin(a) * r])
    }
  }
  return pts
}

function circlePoints(r, segments = 48) {
  const pts = []
  for (let i = 0; i < segments; i++) {
    const a = (i / segments) * Math.PI * 2
    pts.push([r + Math.cos(a) * r, r + Math.sin(a) * r])
  }
  return pts
}

// A rough side-profile goose (tail, back, neck, beak, breast, belly), hand-authored
// as fractions of its bounding box and scaled to the requested size. It only has to
// read as "goose-shaped", not be anatomically exact.
const GOOSE_OUTLINE_NORM = [
  [0.02, 0.55], [0.08, 0.42], [0.20, 0.30], [0.34, 0.22], [0.44, 0.20],
  [0.52, 0.14], [0.58, 0.06], [0.64, 0.02], [0.78, 0.05], [0.86, 0.09],
  [0.77, 0.10], [0.68, 0.14], [0.60, 0.22], [0.54, 0.32], [0.50, 0.44],
  [0.44, 0.58], [0.32, 0.66], [0.18, 0.66], [0.10, 0.62], [0.04, 0.60],
]

function goosePoints(w, h) {
  const hh = h ?? w * 0.72
  return GOOSE_OUTLINE_NORM.map(([nx, ny]) => [nx * w, ny * hh])
}

export const OUTLINE_PRESETS = ['rectangle', 'rounded-rectangle', 'circle', 'goose']

export function outlinePoints(preset, opts = {}) {
  const w = opts.width ?? 150, h = opts.height ?? 100
  switch (preset) {
    case 'rectangle': return rectanglePoints(w, h)
    case 'rounded-rectangle': return roundedRectanglePoints(w, h, opts.radius)
    case 'circle': return circlePoints(Math.min(w, h) / 2, opts.segments)
    case 'goose': return goosePoints(w, opts.height)
    default: return rectanglePoints(w, h)
  }
}

// ------------------------------------------------------------------- document --

export const DEFAULT_NETS = [
  { name: 'GND', color: '#8b98a8' },
  { name: 'PENALTY', color: '#f85149' },
  { name: 'GOAL_1', color: '#3fb950' },
  { name: 'GOAL_2', color: '#58a6ff' },
]

export function newDocument(preset = 'rectangle', opts = {}) {
  return {
    version: 1,
    units: 'mm',
    grid: opts.grid ?? 1.0,
    outline: { points: outlinePoints(preset, opts) },
    nets: (opts.nets || DEFAULT_NETS).map((n) => ({ ...n })),
    objects: [],
  }
}

export function netColor(doc, name) {
  const n = doc.nets.find((x) => x.name === name)
  return n ? n.color : '#8b98a8'
}

export function findObject(doc, id) {
  return doc.objects.find((o) => o.id === id) || null
}

// Returns the editable point list for an object id ('outline' or a trace id),
// or null for holes and unknown ids — they have no vertex list to edit.
export function pointsOf(doc, id) {
  if (id === 'outline') return doc.outline.points
  const o = findObject(doc, id)
  return o && o.points ? o.points : null
}

function clonePoint(p) {
  return [p[0], p[1]]
}

// Applies fn to the object with this id and only counts it as a change (a new
// document) if fn actually returned a different object — this keeps genuine
// no-ops (wrong id, wrong kind) from growing the undo history.
function mapObject(doc, id, fn) {
  let changed = false
  const objects = doc.objects.map((o) => {
    if (o.id !== id) return o
    const next = fn(o)
    if (next !== o) changed = true
    return next
  })
  return changed ? { ...doc, objects } : doc
}

// --------------------------------------------------------------------- ops --
// Every op returns a new document (or the same reference, unchanged, if the
// op did not apply). None of them mutate `doc`.

export function setOutline(doc, points) {
  return { ...doc, outline: { points: points.map(clonePoint) } }
}

export function addTrace(doc, { id, net, width, points }) {
  const obj = { id: id || uid('t'), kind: 'trace', net, width, points: points.map(clonePoint) }
  return { ...doc, objects: [...doc.objects, obj] }
}

export function updateTrace(doc, id, patch) {
  return mapObject(doc, id, (o) => (o.kind === 'trace' ? { ...o, ...patch } : o))
}

export function moveVertex(doc, id, index, point) {
  if (id === 'outline') {
    const pts = doc.outline.points
    if (index < 0 || index >= pts.length) return doc
    const next = pts.slice()
    next[index] = clonePoint(point)
    return { ...doc, outline: { points: next } }
  }
  return mapObject(doc, id, (o) => {
    if (!o.points || index < 0 || index >= o.points.length) return o
    const pts = o.points.slice()
    pts[index] = clonePoint(point)
    return { ...o, points: pts }
  })
}

// Inserts a new vertex right after `segmentIndex` (the segment from point[i] to
// point[i+1], wrapping for the closed outline).
export function insertVertex(doc, id, segmentIndex, point) {
  if (id === 'outline') {
    const pts = doc.outline.points
    if (segmentIndex < 0 || segmentIndex >= pts.length) return doc
    const next = pts.slice()
    next.splice(segmentIndex + 1, 0, clonePoint(point))
    return { ...doc, outline: { points: next } }
  }
  return mapObject(doc, id, (o) => {
    if (!o.points || segmentIndex < 0 || segmentIndex >= o.points.length - 1) return o
    const pts = o.points.slice()
    pts.splice(segmentIndex + 1, 0, clonePoint(point))
    return { ...o, points: pts }
  })
}

export function deleteVertex(doc, id, index) {
  if (id === 'outline') {
    const pts = doc.outline.points
    if (pts.length <= 3 || index < 0 || index >= pts.length) return doc // never break the outline below a triangle
    const next = pts.slice()
    next.splice(index, 1)
    return { ...doc, outline: { points: next } }
  }
  const obj = findObject(doc, id)
  if (!obj || !obj.points || index < 0 || index >= obj.points.length) return doc
  if (obj.points.length <= 2) return deleteObject(doc, id) // one segment left: dropping a vertex drops the trace
  return mapObject(doc, id, (o) => {
    const pts = o.points.slice()
    pts.splice(index, 1)
    return { ...o, points: pts }
  })
}

export function setNet(doc, id, net) {
  return mapObject(doc, id, (o) => ({ ...o, net }))
}

// Generic "size" setter: width for a trace, diameter for a hole — the inspector
// shows one field either way, so one op covers both.
export function setWidth(doc, id, value) {
  return mapObject(doc, id, (o) => (o.kind === 'hole' ? { ...o, d: value } : { ...o, width: value }))
}

export function addHole(doc, { id, at, d = 1.2, role = 'generic', net = null }) {
  const obj = { id: id || uid('h'), kind: 'hole', d, at: clonePoint(at), role, net }
  return { ...doc, objects: [...doc.objects, obj] }
}

export function moveHole(doc, id, at) {
  return mapObject(doc, id, (o) => (o.kind === 'hole' ? { ...o, at: clonePoint(at) } : o))
}

export function deleteObject(doc, id) {
  const next = doc.objects.filter((o) => o.id !== id)
  return next.length === doc.objects.length ? doc : { ...doc, objects: next }
}

// ------------------------------------------------------------- undo/redo --

export const HISTORY_LIMIT = 50

const OPS = {
  setOutline: (doc, a) => setOutline(doc, a.points),
  addTrace: (doc, a) => addTrace(doc, a),
  updateTrace: (doc, a) => updateTrace(doc, a.id, a.patch),
  moveVertex: (doc, a) => moveVertex(doc, a.id, a.index, a.point),
  insertVertex: (doc, a) => insertVertex(doc, a.id, a.segmentIndex, a.point),
  deleteVertex: (doc, a) => deleteVertex(doc, a.id, a.index),
  setNet: (doc, a) => setNet(doc, a.id, a.net),
  setWidth: (doc, a) => setWidth(doc, a.id, a.width),
  addHole: (doc, a) => addHole(doc, a),
  moveHole: (doc, a) => moveHole(doc, a.id, a.at),
  deleteObject: (doc, a) => deleteObject(doc, a.id),
}

export function initHistory(doc) {
  return { present: doc, past: [], future: [] }
}

// One reducer for everything: undo/redo bookkeeping plus dispatching document
// ops by `action.type`. Unknown actions and no-op edits leave state untouched
// (same reference), so React won't re-render and the history won't grow.
export function historyReducer(state, action) {
  if (action.type === 'undo') {
    if (state.past.length === 0) return state
    const present = state.past[state.past.length - 1]
    return { present, past: state.past.slice(0, -1), future: [state.present, ...state.future] }
  }
  if (action.type === 'redo') {
    if (state.future.length === 0) return state
    const [present, ...rest] = state.future
    return { present, past: [...state.past, state.present].slice(-HISTORY_LIMIT), future: rest }
  }
  if (action.type === 'load') {
    return initHistory(action.doc)
  }
  const op = OPS[action.type]
  if (!op) return state
  const next = op(state.present, action)
  if (next === state.present) return state
  return { present: next, past: [...state.past, state.present].slice(-HISTORY_LIMIT), future: [] }
}
