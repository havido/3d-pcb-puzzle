// The SVG board canvas. Coordinates are millimetres with Y pointing down, same
// as KiCad — since SVG's Y also points down, the viewBox maps 1 unit to 1 mm
// with no flip (unlike Viewer.jsx's 3D scene, which is Y-up and does flip).
//
// All hit-testing (which vertex/segment/object the pointer is over) happens
// here, at the container level, rather than as per-shape event handlers — that
// keeps the select/insert/drag priority rules in one place instead of racing
// on z-order.
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { dist, distToSegment, netColor, pointsOf, polygonBounds, snapAngle, snapToGrid } from './doc.js'

const MIN_SCALE = 0.04   // mm per screen px, i.e. how far in you can zoom
const MAX_SCALE = 6
const HIT_PX = 9         // vertex/segment hit radius, in screen pixels

function ptsToStr(points) {
  return points.map((p) => `${p[0]},${p[1]}`).join(' ')
}

function fitCam(doc, rect) {
  const bb = polygonBounds(doc.outline.points)
  const w = Math.max(bb.maxX - bb.minX, 10)
  const h = Math.max(bb.maxY - bb.minY, 10)
  const cx = (bb.minX + bb.maxX) / 2
  const cy = (bb.minY + bb.maxY) / 2
  const pxW = rect?.width || 800
  const pxH = rect?.height || 600
  const margin = 1.25
  const scale = Math.max((w * margin) / pxW, (h * margin) / pxH)
  return { cx, cy, scale: Math.min(Math.max(scale, MIN_SCALE), MAX_SCALE) }
}

function clamp(v, lo, hi) {
  return Math.min(Math.max(v, lo), hi)
}

// Applies an in-progress drag preview so the shape follows the pointer before
// the edit is committed as a real (undoable) op on mouse-up.
function livePoints(id, points, dragPreview) {
  if (!dragPreview || dragPreview.id !== id) return points
  if (dragPreview.index !== undefined) {
    const next = points.slice()
    next[dragPreview.index] = dragPreview.point
    return next
  }
  if (dragPreview.delta) {
    const [dx, dy] = dragPreview.delta
    return points.map(([x, y]) => [x + dx, y + dy])
  }
  return points
}

function liveAt(hole, dragPreview) {
  if (!dragPreview || dragPreview.id !== hole.id || !dragPreview.delta) return hole.at
  const [dx, dy] = dragPreview.delta
  return [hole.at[0] + dx, hole.at[1] + dy]
}

export default function Canvas({ doc, dispatch, tool, activeNet, activeWidth, selection, setSelection, violations, fitToken }) {
  const wrapRef = useRef(null)
  const svgRef = useRef(null)
  const [rect, setRect] = useState(null)
  const [cam, setCam] = useState(() => fitCam(doc, null))
  const firstFit = useRef(false)
  const [spaceHeld, setSpaceHeld] = useState(false)
  const [draft, setDraft] = useState(null)          // {points} while drawing a trace/outline
  const [cursorMm, setCursorMm] = useState(null)
  const [dragPreview, setDragPreview] = useState(null)
  const dragRef = useRef(null)

  // Track container size so the viewBox always matches its pixel aspect ratio
  // (avoids stretching); also does the one-time fit-to-outline on first mount.
  useLayoutEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const update = () => {
      const r = el.getBoundingClientRect()
      setRect(r)
      if (!firstFit.current) { firstFit.current = true; setCam(fitCam(doc, r)) }
    }
    update()
    const ro = new ResizeObserver(update)
    ro.observe(el)
    return () => ro.disconnect()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    function onKeyDown(e) {
      const tag = document.activeElement?.tagName
      const typing = tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA'
      if (e.code === 'Space' && !typing) { setSpaceHeld(true); e.preventDefault() }
      if (typing) return
      if (e.key === 'Escape') { setDraft(null) }
      if (e.key === 'Enter') { commitDraft() }
      if (e.key === 'Backspace' || e.key === 'Delete') { deleteSelection(); e.preventDefault() }
    }
    function onKeyUp(e) { if (e.code === 'Space') setSpaceHeld(false) }
    window.addEventListener('keydown', onKeyDown)
    window.addEventListener('keyup', onKeyUp)
    return () => { window.removeEventListener('keydown', onKeyDown); window.removeEventListener('keyup', onKeyUp) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft, selection, doc, tool])

  // Changing tool abandons whatever was being drawn, rather than leaving it on screen.
  useEffect(() => { setDraft(null) }, [tool])

  // Re-fit when the document is replaced (a preset, or opening a real board), otherwise
  // a board somewhere else in the coordinate plane lands off-screen.
  const docRef = useRef(doc)
  docRef.current = doc
  useEffect(() => {
    if (fitToken === undefined) return
    setCam(fitCam(docRef.current, wrapRef.current?.getBoundingClientRect()))
  }, [fitToken])

  const viewW = (rect?.width || 800) * cam.scale
  const viewH = (rect?.height || 600) * cam.scale
  const minX = cam.cx - viewW / 2
  const minY = cam.cy - viewH / 2

  function screenToMm(e) {
    const r = wrapRef.current.getBoundingClientRect()
    const px = e.clientX - r.left, py = e.clientY - r.top
    return [minX + px * cam.scale, minY + py * cam.scale]
  }

  function hitTol() { return HIT_PX * cam.scale }

  function deleteSelection() {
    if (!selection) return
    if (selection.vertexIndex !== undefined) {
      dispatch({ type: 'deleteVertex', id: selection.id, index: selection.vertexIndex })
      setSelection({ id: selection.id })
    } else if (selection.id !== 'outline') {
      dispatch({ type: 'deleteObject', id: selection.id })
      setSelection(null)
    }
  }

  // Commits outside any state updater: React can run an updater twice, and dispatching
  // from inside one added the trace twice.
  function commitDraft() {
    if (draft && draft.points.length >= 2) {
      if (tool === 'trace') dispatch({ type: 'addTrace', net: activeNet, width: activeWidth, points: draft.points })
      else if (tool === 'outline') dispatch({ type: 'setOutline', points: draft.points })
    }
    setDraft(null)
  }

  // A pure function of (prior draft, raw point) — safe under StrictMode's
  // double-invoked updaters, unlike mutating a variable captured by the closure.
  function nextDraftPoint(mm) {
    setDraft((d) => {
      let pt = snapToGrid(mm, doc.grid)
      if (d && d.points.length > 0) pt = snapToGrid(snapAngle(d.points[d.points.length - 1], pt), doc.grid)
      return d ? { points: [...d.points, pt] } : { points: [pt] }
    })
  }

  // ------------------------------------------------------------ pointer handling --

  function handleWheel(e) {
    e.preventDefault()
    const r = wrapRef.current.getBoundingClientRect()
    const px = e.clientX - r.left, py = e.clientY - r.top
    const factor = Math.exp(e.deltaY * 0.0015)
    setCam((c) => {
      const scale = clamp(c.scale * factor, MIN_SCALE, MAX_SCALE)
      const oldMinX = c.cx - (r.width * c.scale) / 2
      const oldMinY = c.cy - (r.height * c.scale) / 2
      const mmX = oldMinX + px * c.scale
      const mmY = oldMinY + py * c.scale
      const newMinX = mmX - px * scale
      const newMinY = mmY - py * scale
      return { cx: newMinX + (r.width * scale) / 2, cy: newMinY + (r.height * scale) / 2, scale }
    })
  }

  function handleMouseDown(e) {
    if (spaceHeld || e.button === 1) {
      dragRef.current = { kind: 'pan', startScreen: [e.clientX, e.clientY], startCam: cam }
      e.preventDefault()
      return
    }
    if (tool !== 'select' || e.button !== 0) return
    const mm = screenToMm(e)
    const tol = hitTol()

    // 1. a vertex of the currently selected trace/outline
    const selPts = selection ? pointsOf(doc, selection.id) : null
    if (selPts) {
      for (let i = 0; i < selPts.length; i++) {
        if (dist(selPts[i], mm) <= tol) {
          dragRef.current = { kind: 'vertex', id: selection.id, index: i, moved: false }
          return
        }
      }
      // 2. alt-click a segment of the selected object -> insert a vertex there and drag it.
      //    Without alt, a drag on the body moves the whole object (case 3).
      const closed = selection.id === 'outline'
      const segCount = e.altKey ? (closed ? selPts.length : selPts.length - 1) : 0
      for (let i = 0; i < segCount; i++) {
        const a = selPts[i], b = selPts[(i + 1) % selPts.length]
        if (distToSegment(mm, a, b) <= tol) {
          const point = snapToGrid(mm, doc.grid)
          dispatch({ type: 'insertVertex', id: selection.id, segmentIndex: i, point })
          dragRef.current = { kind: 'vertex', id: selection.id, index: i + 1, moved: false }
          return
        }
      }
    }

    // 3. any object's body -> select it and prepare to drag the whole thing
    for (const h of doc.objects) {
      if (h.kind === 'hole' && dist(mm, h.at) <= h.d / 2 + tol) {
        setSelection({ id: h.id })
        dragRef.current = { kind: 'object', id: h.id, start: mm, moved: false }
        return
      }
    }
    for (const t of doc.objects) {
      if (t.kind !== 'trace') continue
      for (let i = 0; i < t.points.length - 1; i++) {
        if (distToSegment(mm, t.points[i], t.points[i + 1]) <= t.width / 2 + tol) {
          setSelection({ id: t.id })
          dragRef.current = { kind: 'object', id: t.id, start: mm, moved: false }
          return
        }
      }
    }
    const outline = doc.outline.points
    for (let i = 0; i < outline.length; i++) {
      if (distToSegment(mm, outline[i], outline[(i + 1) % outline.length]) <= tol) {
        setSelection({ id: 'outline' })
        dragRef.current = { kind: 'object', id: 'outline', start: mm, moved: false }
        return
      }
    }
    setSelection(null)
  }

  function handleMouseMove(e) {
    const mm = screenToMm(e)
    setCursorMm(mm)
    const d = dragRef.current
    if (!d) return
    if (d.kind === 'pan') {
      const dx = (e.clientX - d.startScreen[0]) * cam.scale
      const dy = (e.clientY - d.startScreen[1]) * cam.scale
      setCam({ ...d.startCam, cx: d.startCam.cx - dx, cy: d.startCam.cy - dy })
      return
    }
    if (d.kind === 'vertex') {
      d.moved = true
      setDragPreview({ id: d.id, index: d.index, point: snapToGrid(mm, doc.grid) })
      return
    }
    if (d.kind === 'object') {
      d.moved = true
      setDragPreview({ id: d.id, delta: [mm[0] - d.start[0], mm[1] - d.start[1]] })
      return
    }
  }

  function translateObject(id, [dx, dy]) {
    if (id === 'outline') {
      dispatch({ type: 'setOutline', points: doc.outline.points.map(([x, y]) => [x + dx, y + dy]) })
      return
    }
    const obj = doc.objects.find((o) => o.id === id)
    if (!obj) return
    if (obj.kind === 'trace') {
      dispatch({ type: 'updateTrace', id, patch: { points: obj.points.map(([x, y]) => [x + dx, y + dy]) } })
    } else if (obj.kind === 'hole') {
      dispatch({ type: 'moveHole', id, at: [obj.at[0] + dx, obj.at[1] + dy] })
    }
  }

  function handleMouseUp() {
    const d = dragRef.current
    dragRef.current = null
    if (!d) return
    if (d.kind === 'vertex') {
      if (d.moved && dragPreview) dispatch({ type: 'moveVertex', id: d.id, index: d.index, point: dragPreview.point })
      else setSelection({ id: d.id, vertexIndex: d.index })
    } else if (d.kind === 'object' && d.moved && dragPreview) {
      translateObject(d.id, dragPreview.delta)
    }
    setDragPreview(null)
  }

  function handleClick(e) {
    if (spaceHeld || e.detail > 1) return      // the 2nd click of a double-click finishes, it doesn't add
    const mm = screenToMm(e)
    if (tool === 'hole') {
      dispatch({ type: 'addHole', at: snapToGrid(mm, doc.grid), d: 1.2, role: 'generic', net: activeNet })
    } else if (tool === 'trace' || tool === 'outline') {
      nextDraftPoint(mm)
    }
  }

  function handleDoubleClick() {
    if (tool === 'trace' || tool === 'outline') commitDraft()
  }

  // -------------------------------------------------------------------- render --

  const violatedIds = useMemo(() => new Set(violations.map((v) => v.objectId)), [violations])
  const outlinePts = livePoints('outline', doc.outline.points, dragPreview)
  const outlineBad = violatedIds.has('outline')
  const selPts = selection ? pointsOf(doc, selection.id) : null
  const selLivePts = selPts ? livePoints(selection.id, selPts, dragPreview) : null

  const previewNext = draft && cursorMm
    ? snapToGrid(draft.points.length ? snapAngle(draft.points[draft.points.length - 1], snapToGrid(cursorMm, doc.grid)) : cursorMm, doc.grid)
    : null

  return (
    <div
      className={`design-canvas tool-${tool}${spaceHeld ? ' panning' : ''}`}
      ref={wrapRef}
      onWheel={handleWheel}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
      onClick={handleClick}
      onDoubleClick={handleDoubleClick}
    >
      <svg ref={svgRef} width="100%" height="100%" viewBox={`${minX} ${minY} ${viewW} ${viewH}`} preserveAspectRatio="xMidYMid meet">
        <defs>
          <pattern id="grid-minor" width={doc.grid} height={doc.grid} patternUnits="userSpaceOnUse">
            <path d={`M ${doc.grid} 0 L 0 0 0 ${doc.grid}`} fill="none" stroke="#1c2432" strokeWidth={cam.scale * 0.6} />
          </pattern>
          <pattern id="grid-major" width={doc.grid * 10} height={doc.grid * 10} patternUnits="userSpaceOnUse">
            <path d={`M ${doc.grid * 10} 0 L 0 0 0 ${doc.grid * 10}`} fill="none" stroke="#26324a" strokeWidth={cam.scale * 0.8} />
          </pattern>
        </defs>

        <rect x={minX} y={minY} width={viewW} height={viewH} fill="url(#grid-minor)" />
        <rect x={minX} y={minY} width={viewW} height={viewH} fill="url(#grid-major)" />

        {outlineBad && (
          <polygon points={ptsToStr(outlinePts)} fill="none" stroke="var(--bad)" strokeWidth={cam.scale * 10} opacity={0.35} />
        )}
        <polygon
          points={ptsToStr(outlinePts)}
          fill="rgba(217,130,43,0.05)"
          stroke={outlineBad ? 'var(--bad)' : 'var(--ink)'}
          strokeWidth={outlineBad ? cam.scale * 2.5 : cam.scale * 1.5}
        />

        {doc.objects.filter((o) => o.kind === 'trace').map((t) => {
          const pts = livePoints(t.id, t.points, dragPreview)
          const bad = violatedIds.has(t.id)
          const isSel = selection?.id === t.id
          return (
            <g key={t.id}>
              {bad && (
                <polyline points={ptsToStr(pts)} fill="none" stroke="var(--bad)" strokeWidth={t.width + 3}
                           strokeLinecap="round" strokeLinejoin="round" opacity={0.4} />
              )}
              <polyline points={ptsToStr(pts)} fill="none" stroke={netColor(doc, t.net)} strokeWidth={t.width}
                         strokeLinecap="round" strokeLinejoin="round" opacity={isSel ? 1 : 0.88} />
            </g>
          )
        })}

        {doc.objects.filter((o) => o.kind === 'hole').map((h) => {
          const at = liveAt(h, dragPreview)
          const bad = violatedIds.has(h.id)
          const isSel = selection?.id === h.id
          return (
            <g key={h.id}>
              {bad && <circle cx={at[0]} cy={at[1]} r={h.d / 2 + 1.5} fill="none" stroke="var(--bad)" strokeWidth={cam.scale * 4} opacity={0.4} />}
              <circle cx={at[0]} cy={at[1]} r={h.d / 2} fill="var(--bg)" stroke={h.net ? netColor(doc, h.net) : 'var(--dim)'} strokeWidth={cam.scale * 1.5} />
              {h.role === 'pogo' && (
                <path d={`M ${at[0] - h.d / 3} ${at[1]} L ${at[0] + h.d / 3} ${at[1]} M ${at[0]} ${at[1] - h.d / 3} L ${at[0]} ${at[1] + h.d / 3}`}
                      stroke={h.net ? netColor(doc, h.net) : 'var(--dim)'} strokeWidth={cam.scale * 1.2} />
              )}
              {isSel && <circle cx={at[0]} cy={at[1]} r={h.d / 2 + cam.scale * 6} fill="none" stroke="var(--copper)" strokeWidth={cam.scale * 1.2} strokeDasharray={`${cam.scale * 3},${cam.scale * 2}`} />}
            </g>
          )
        })}

        {/* draft in progress: the trace/outline currently being drawn */}
        {draft && (
          <>
            <polyline points={ptsToStr(draft.points)} fill="none"
                       stroke={tool === 'trace' ? netColor(doc, activeNet) : 'var(--ink)'}
                       strokeWidth={tool === 'trace' ? activeWidth : cam.scale * 1.5}
                       strokeLinecap="round" strokeLinejoin="round" opacity={0.8} />
            {previewNext && (
              <line x1={draft.points[draft.points.length - 1][0]} y1={draft.points[draft.points.length - 1][1]}
                    x2={previewNext[0]} y2={previewNext[1]} stroke="var(--dim)" strokeWidth={cam.scale * 1.2}
                    strokeDasharray={`${cam.scale * 3},${cam.scale * 2}`} />
            )}
            {draft.points.map((p, i) => (
              <circle key={i} cx={p[0]} cy={p[1]} r={cam.scale * 4} fill="var(--copper)" />
            ))}
          </>
        )}

        {/* selection handles */}
        {selLivePts && selLivePts.map((p, i) => {
          const isVertexSel = selection.vertexIndex === i
          const r = cam.scale * (isVertexSel ? 6 : 4.5)
          return (
            <rect key={i} x={p[0] - r} y={p[1] - r} width={r * 2} height={r * 2}
                  fill={isVertexSel ? 'var(--copper)' : '#fff'} stroke="#000" strokeWidth={cam.scale} />
          )
        })}
      </svg>

      <div className="design-canvas-controls">
        <button onClick={() => setCam(fitCam(doc, wrapRef.current?.getBoundingClientRect()))}>Fit</button>
        <span className="hint">
          {cursorMm ? `${cursorMm[0].toFixed(1)}, ${cursorMm[1].toFixed(1)} mm · ` : ''}
          space+drag or middle mouse to pan · wheel to zoom
          {(tool === 'trace' || tool === 'outline') && ' · enter/double-click to finish, esc to cancel'}
          {tool === 'select' && ' · drag to move, alt-click an edge to add a point'}
        </span>
      </div>
    </div>
  )
}
