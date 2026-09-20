// Layout for the Design tab (plan §1): tools + nets + outline presets on the
// left, the canvas in the middle, inspector + live rules on the right.
// The document lives in a useReducer history (doc.js) so undo/redo is free;
// selection and tool state are ordinary UI state, not part of the document.
import { useCallback, useEffect, useMemo, useReducer, useState } from 'react'
import { designImport, getSamples } from '../api.js'
import Canvas from './Canvas.jsx'
import { historyReducer, initHistory, newDocument, outlinePoints, polygonBounds, withNetColors } from './doc.js'
import { checkRules } from './rules.js'

const STORAGE_KEY = 'design.doc.v1'

const TOOLS = [
  { id: 'select', label: 'Select' },
  { id: 'trace', label: 'Trace' },
  { id: 'hole', label: 'Hole' },
  { id: 'outline', label: 'Outline' },
]

const PRESETS = [
  { id: 'rectangle', label: 'Rectangle' },
  { id: 'rounded-rectangle', label: 'Rounded rect' },
  { id: 'circle', label: 'Circle' },
  { id: 'goose', label: 'Goose' },
]

function loadInitialDoc() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw)
      if (parsed && parsed.version === 1 && parsed.outline?.points?.length >= 3) return parsed
    }
  } catch {
    // corrupt or blocked storage — fall through to a fresh document
  }
  return newDocument('rectangle', { width: 150, height: 100 })
}

export default function DesignTab({ onConvert }) {
  const [history, dispatchHistory] = useReducer(historyReducer, undefined, () => initHistory(loadInitialDoc()))
  const doc = history.present
  const dispatch = useCallback((action) => dispatchHistory(action), [])

  const [tool, setTool] = useState('select')
  const [selection, setSelection] = useState(null)
  const [activeNet, setActiveNet] = useState(doc.nets[0]?.name || null)
  const [activeWidth, setActiveWidth] = useState(3.0)
  // Raw text of the width/diameter inspector field, kept separate from the document
  // so mid-edit states (empty, a trailing ".") can be typed without either fighting
  // the input or ever committing a non-positive size to the doc.
  const [sizeText, setSizeText] = useState('')
  const [samples, setSamples] = useState([])
  const [busy, setBusy] = useState(null)               // 'convert' | 'open' while the API works
  const [error, setError] = useState(null)
  const [fitToken, setFitToken] = useState(0)

  useEffect(() => { getSamples().then(setSamples).catch(() => setSamples([])) }, [])

  // Open one of the real boards as an editable document: the fastest way to show that
  // this draws the same thing the converter prints.
  async function openSample(sample) {
    setBusy('open'); setError(null)
    try {
      const { document } = await designImport(sample.board_id)
      dispatch({ type: 'load', doc: withNetColors(document) })
      setSelection(null)
      setFitToken((n) => n + 1)
    } catch (e) { setError(e.message) } finally { setBusy(null) }
  }

  async function convert() {
    setBusy('convert'); setError(null)
    try { await onConvert?.(doc) } catch (e) { setError(e.message); setBusy(null) }
  }

  useEffect(() => {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(doc)) } catch { /* storage full/blocked — not fatal */ }
  }, [doc])

  // If undo/redo or a delete removes the selected object, drop the selection.
  useEffect(() => {
    if (!selection || selection.id === 'outline') return
    if (!doc.objects.some((o) => o.id === selection.id)) setSelection(null)
  }, [doc, selection])

  const violations = useMemo(() => checkRules(doc), [doc])

  const selected = !selection ? null
    : selection.id === 'outline' ? { id: 'outline', kind: 'outline', points: doc.outline.points }
    : doc.objects.find((o) => o.id === selection.id) || null

  // Reset the field text when the selection itself changes (a different object, or
  // none). Deliberately not keyed on the object's width/d: that would overwrite
  // whatever the user is mid-typing every time a keystroke commits a valid value.
  useEffect(() => {
    if (selected && selected.kind === 'trace') setSizeText(String(selected.width))
    else if (selected && selected.kind === 'hole') setSizeText(String(selected.d))
    else setSizeText('')
  }, [selected?.id])

  // Shared by the Width and Diameter fields: always show what was typed, but only
  // ever forward a positive, finite number to the document — an empty or partial
  // value (e.g. "2.") is held here until it parses, never written as 0.
  function handleSizeChange(text) {
    setSizeText(text)
    const value = Number(text)
    if (text.trim() !== '' && Number.isFinite(value) && value > 0) {
      dispatch({ type: 'setWidth', id: selected.id, width: value })
    }
  }

  // Clicking a net always makes it the active net for new objects; if something is
  // already selected, it also re-assigns that object — the behaviour most people
  // expect on the first try.
  function selectNet(name) {
    setActiveNet(name)
    if (selected && (selected.kind === 'trace' || selected.kind === 'hole')) {
      dispatch({ type: 'setNet', id: selected.id, net: name })
    }
  }

  function applyPreset(preset) {
    const bb = polygonBounds(doc.outline.points)
    const width = Math.max(bb.maxX - bb.minX, 20)
    const height = Math.max(bb.maxY - bb.minY, 20)
    dispatch({ type: 'setOutline', points: outlinePoints(preset, { width, height }) })
    setSelection(null)
    setFitToken((n) => n + 1)
  }

  return (
    <div className="design">
      <aside className="design-left">
        <h2>Tools</h2>
        <div className="tool-list">
          {TOOLS.map((t) => (
            <button key={t.id} className={tool === t.id ? 'on' : ''} onClick={() => { setTool(t.id); setSelection(null) }}>
              {t.label}
            </button>
          ))}
        </div>

        <h2>Nets</h2>
        {selected && (selected.kind === 'trace' || selected.kind === 'hole') && (
          <p className="dim tip">Click a net to move the selection onto it.</p>
        )}
        <ul className="net-list">
          {doc.nets.map((n) => (
            <li key={n.name}>
              <button className={activeNet === n.name ? 'on' : ''} onClick={() => selectNet(n.name)}>
                <span className="swatch" style={{ background: n.color }} />
                {n.name}
              </button>
            </li>
          ))}
        </ul>

        <h2>Outline presets</h2>
        <div className="preset-list">
          {PRESETS.map((p) => (
            <button key={p.id} onClick={() => applyPreset(p.id)}>{p.label}</button>
          ))}
        </div>

        <h2>Open a real board</h2>
        <div className="preset-list">
          {samples.map((s) => (
            <button key={s.key} disabled={busy !== null} onClick={() => openSample(s)}>{s.name}</button>
          ))}
          {samples.length === 0 && <span className="dim">no API</span>}
        </div>
      </aside>

      <div className="design-mid">
        <div className="design-toolbar">
          <button disabled={history.past.length === 0} onClick={() => dispatch({ type: 'undo' })} title="Undo">&#8630; Undo</button>
          <button disabled={history.future.length === 0} onClick={() => dispatch({ type: 'redo' })} title="Redo">&#8631; Redo</button>
          {tool === 'trace' && (
            <label className="width-field">
              width
              <input type="number" min="0.5" step="0.1" value={activeWidth}
                     onChange={(e) => setActiveWidth(Number(e.target.value) || 0.5)} />
              mm
            </label>
          )}
          <span className="dim">{doc.objects.length} object{doc.objects.length === 1 ? '' : 's'}</span>
        </div>
        <Canvas
          doc={doc}
          dispatch={dispatch}
          tool={tool}
          activeNet={activeNet}
          activeWidth={activeWidth}
          selection={selection}
          setSelection={setSelection}
          violations={violations}
          fitToken={fitToken}
        />
      </div>

      <aside className="design-right">
        <h2>Inspector</h2>
        {!selected && <p className="dim">Nothing selected.</p>}
        {selected && selected.kind === 'trace' && (
          <div className="inspector-fields">
            <label>
              Width (mm)
              <input type="number" min="0.1" step="0.1" value={sizeText}
                     onChange={(e) => handleSizeChange(e.target.value)} />
            </label>
            <label>
              Net
              <select value={selected.net || ''} onChange={(e) => dispatch({ type: 'setNet', id: selected.id, net: e.target.value })}>
                {doc.nets.map((n) => <option key={n.name} value={n.name}>{n.name}</option>)}
              </select>
            </label>
            <div className="kv"><span>Points</span><strong>{selected.points.length}</strong></div>
          </div>
        )}
        {selected && selected.kind === 'hole' && (
          <div className="inspector-fields">
            <label>
              Diameter (mm)
              <input type="number" min="0.1" step="0.1" value={sizeText}
                     onChange={(e) => handleSizeChange(e.target.value)} />
            </label>
            <label>
              Net
              <select value={selected.net || ''} onChange={(e) => dispatch({ type: 'setNet', id: selected.id, net: e.target.value })}>
                <option value="">(none)</option>
                {doc.nets.map((n) => <option key={n.name} value={n.name}>{n.name}</option>)}
              </select>
            </label>
            <div className="kv"><span>Role</span><strong>{selected.role}</strong></div>
          </div>
        )}
        {selected && selected.kind === 'outline' && (
          <div className="inspector-fields">
            <div className="kv"><span>Points</span><strong>{selected.points.length}</strong></div>
          </div>
        )}

        <h2>Rules {violations.length > 0 && <em>({violations.length})</em>}</h2>
        {violations.length === 0 && <p className="ok">Everything checks out.</p>}
        <ul className="rule-list">
          {violations.map((v, i) => (
            <li key={i} className={selection?.id === v.objectId ? 'clickable active' : 'clickable'}
                onClick={() => setSelection({ id: v.objectId })}>
              {v.message}
            </li>
          ))}
        </ul>

        <h2>Make it real</h2>
        <button className="convert-button" disabled={busy !== null} onClick={convert}>
          {busy === 'convert' ? 'Converting…' : 'Convert → 3D'}
        </button>
        <p className="dim tip">Writes a KiCad board from this drawing and runs it through the converter.</p>
        {error && <p className="design-error">{error}</p>}
      </aside>
    </div>
  )
}
