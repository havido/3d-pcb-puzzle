// Live fabrication checks (plan §1). These mirror the numbers already measured
// into CLAUDE.md / docs/PIPELINE.md (moats + rims sharing at 4.6 mm, etc.) — if
// the coupon test changes a number, change it here and the server's checks stay
// the source of truth for the actual convert step.
//
// Every check is a pure function of the document; distances use the
// segment/point maths from doc.js, which the plan explicitly allows to be
// approximate rather than exact-CAD-kernel precise.
import { dist, distToPolygon, distToSegment, midpoint, pointInPolygon, polygonBounds, segmentDistance } from './doc.js'

export const DEFAULT_RULES = {
  minTraceWidth: 3.0,   // mm — the tape shears cleanly at this width
  minNetGap: 4.6,       // mm — 2 * (moat width + rim width); closer and the moats merge
  minEdgeMargin: 4.0,   // mm — room for the moat and rim at the board edge
  minHoleD: 1.0,        // mm — printable
  maxBoardSize: 180,    // mm — the printer bed
}

function labelOf(obj) {
  const kind = obj.kind === 'trace' ? 'trace' : 'hole'
  return obj.net ? `${kind} ${obj.net}` : `${kind} ${obj.id}`
}

function copperGap(a, b) {
  const aPts = a.kind === 'trace' ? a.points : [a.at]
  const bPts = b.kind === 'trace' ? b.points : [b.at]
  const aHalf = a.kind === 'trace' ? a.width / 2 : a.d / 2
  const bHalf = b.kind === 'trace' ? b.width / 2 : b.d / 2

  let best = Infinity
  let at = midpoint([aPts[0], bPts[0]])

  if (a.kind === 'trace' && b.kind === 'trace') {
    for (let i = 0; i < aPts.length - 1; i++) {
      for (let j = 0; j < bPts.length - 1; j++) {
        const d = segmentDistance(aPts[i], aPts[i + 1], bPts[j], bPts[j + 1])
        if (d < best) { best = d; at = midpoint([aPts[i], aPts[i + 1], bPts[j], bPts[j + 1]]) }
      }
    }
  } else if (a.kind === 'trace' && b.kind === 'hole') {
    for (let i = 0; i < aPts.length - 1; i++) {
      const d = distToSegment(bPts[0], aPts[i], aPts[i + 1])
      if (d < best) { best = d; at = midpoint([bPts[0], aPts[i], aPts[i + 1]]) }
    }
  } else if (a.kind === 'hole' && b.kind === 'trace') {
    for (let j = 0; j < bPts.length - 1; j++) {
      const d = distToSegment(aPts[0], bPts[j], bPts[j + 1])
      if (d < best) { best = d; at = midpoint([aPts[0], bPts[j], bPts[j + 1]]) }
    }
  } else {
    best = dist(aPts[0], bPts[0])
    at = midpoint([aPts[0], bPts[0]])
  }

  return { dist: best - aHalf - bHalf, at }
}

// Returns a list of {rule, severity, message, objectId, at} — `at` is a document
// (mm) point useful for drawing a marker or focusing the canvas on the problem.
export function checkRules(doc, rules = DEFAULT_RULES) {
  const violations = []
  const traces = doc.objects.filter((o) => o.kind === 'trace')
  const holes = doc.objects.filter((o) => o.kind === 'hole')
  const outline = doc.outline.points
  const copperObjs = [...traces, ...holes]

  for (const t of traces) {
    if (t.width < rules.minTraceWidth) {
      violations.push({
        rule: 'min-trace-width', severity: 'error', objectId: t.id, at: midpoint(t.points),
        message: `${labelOf(t)}: ${t.width.toFixed(2)} mm wide, needs ≥ ${rules.minTraceWidth} mm`,
      })
    }
  }

  for (const h of holes) {
    if (h.d < rules.minHoleD) {
      violations.push({
        rule: 'min-hole-diameter', severity: 'error', objectId: h.id, at: h.at,
        message: `${labelOf(h)}: ${h.d.toFixed(2)} mm diameter, needs ≥ ${rules.minHoleD} mm`,
      })
    }
  }

  if (outline.length >= 3) {
    const bb = polygonBounds(outline)
    const w = bb.maxX - bb.minX, h = bb.maxY - bb.minY
    if (w > rules.maxBoardSize || h > rules.maxBoardSize) {
      violations.push({
        rule: 'max-board-size', severity: 'error', objectId: 'outline',
        at: [bb.minX + w / 2, bb.minY + h / 2],
        message: `board is ${w.toFixed(0)} × ${h.toFixed(0)} mm, the printer bed tops out at ${rules.maxBoardSize} mm`,
      })
    }

    for (const obj of copperObjs) {
      const halfW = obj.kind === 'trace' ? obj.width / 2 : obj.d / 2
      const pts = obj.kind === 'trace' ? obj.points : [obj.at]
      let minMargin = Infinity
      let worstPoint = pts[0]
      for (const p of pts) {
        const inside = pointInPolygon(p, outline)
        const edgeDist = distToPolygon(p, outline)
        const margin = (inside ? edgeDist : -edgeDist) - halfW
        if (margin < minMargin) { minMargin = margin; worstPoint = p }
      }
      if (minMargin < rules.minEdgeMargin) {
        violations.push({
          rule: 'copper-to-edge', severity: 'error', objectId: obj.id, at: worstPoint,
          message: minMargin < 0
            ? `${labelOf(obj)} crosses or sits outside the board edge`
            : `${labelOf(obj)} is ${minMargin.toFixed(2)} mm from the edge, needs ≥ ${rules.minEdgeMargin} mm`,
        })
      }
    }
  }

  for (let i = 0; i < copperObjs.length; i++) {
    for (let j = i + 1; j < copperObjs.length; j++) {
      const a = copperObjs[i], b = copperObjs[j]
      if (!a.net || !b.net || a.net === b.net) continue
      const gap = copperGap(a, b)
      if (gap.dist < rules.minNetGap) {
        violations.push({
          rule: 'net-clearance', severity: 'error', objectId: a.id, at: gap.at,
          message: `${labelOf(a)} is ${gap.dist.toFixed(2)} mm from ${labelOf(b)}, needs ≥ ${rules.minNetGap} mm between different nets`,
        })
      }
    }
  }

  return violations
}
