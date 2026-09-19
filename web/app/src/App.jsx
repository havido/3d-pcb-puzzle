import { useCallback, useEffect, useRef, useState } from 'react'
import Viewer from './Viewer.jsx'
import { bundleUrl, convertStream, fileUrl, getSamples, getSchema, uploadBoard, API } from './api.js'

const STEP_ORDER = ['parse', 'shapes', 'prepare', 'build', 'export']

// The board and settings live in the URL, so any result can be shared or reloaded.
function readHash() {
  const p = new URLSearchParams(location.hash.slice(1))
  try {
    return { boardId: p.get('board') || null, settings: p.get('s') ? JSON.parse(atob(p.get('s'))) : null }
  } catch {
    return { boardId: null, settings: null }
  }
}

function writeHash(boardId, settings) {
  const p = new URLSearchParams({ board: boardId, s: btoa(JSON.stringify(settings)) })
  history.replaceState(null, '', `#${p}`)
}

export default function App() {
  const [schema, setSchema] = useState(null)
  const [samples, setSamples] = useState([])
  const [board, setBoard] = useState(null)            // {board_id, name}
  const [settings, setSettings] = useState(null)
  const [stages, setStages] = useState([])
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [tab, setTab] = useState('3d')
  const [focus, setFocus] = useState(null)
  const run = useRef(null)

  useEffect(() => {
    Promise.all([getSchema(), getSamples()])
      .then(([sc, sa]) => {
        setSchema(sc)
        setSamples(sa)
        const hash = readHash()
        const start = sa.find((s) => s.board_id === hash.boardId) || sa[0]
        setBoard(start ? { board_id: start.board_id, name: start.name } : null)
        setSettings(hash.settings || sc.defaults)
      })
      .catch((e) => setError(`${e.message} — is the API running at ${API}?`))
  }, [])

  const convert = useCallback((boardId, values) => {
    run.current?.cancel()
    setBusy(true); setError(null); setStages([]); setFocus(null)
    const call = convertStream(boardId, values, (stage) => setStages((s) => [...s, stage]))
    run.current = call
    call.done
      .then((r) => { setResult(r); writeHash(boardId, values) })
      .catch((e) => setError(e.message))
      .finally(() => setBusy(false))
  }, [])

  useEffect(() => {                                    // re-convert shortly after any change
    if (!board || !settings) return
    const t = setTimeout(() => convert(board.board_id, settings), 350)
    return () => clearTimeout(t)
  }, [board, settings, convert])

  const onUpload = async (file) => {
    try {
      setError(null)
      const b = await uploadBoard(file)
      setBoard({ board_id: b.board_id, name: b.name })
    } catch (e) { setError(e.message) }
  }

  const onDrop = (e) => { e.preventDefault(); const f = e.dataTransfer.files?.[0]; if (f) onUpload(f) }
  const set = (name, value) => setSettings((s) => ({ ...s, [name]: value }))

  const b = result?.build
  const done = stages.length >= STEP_ORDER.length

  return (
    <div className="app" onDragOver={(e) => e.preventDefault()} onDrop={onDrop}>
      <header>
        <div>
          <h1>kicad2cad</h1>
          <p>Drop a KiCad board in. Get a 3D-printable circuit board out.</p>
        </div>
        {result && (
          <div className={`headline ${busy ? 'busy' : ''}`}>
            <strong>KiCad → printable board in {result.cached ? '0.0' : result.seconds} s</strong>
            <span>{result.cached ? 'from cache' : 'just now'} · {b.volume_mm3.toFixed(0)} mm³ · {b.triangles.toLocaleString()} triangles
              {b.watertight ? ' · watertight' : ' · NOT watertight'}</span>
          </div>
        )}
      </header>

      <aside className="left">
        <h2>Board</h2>
        <ul className="samples">
          {samples.map((s) => (
            <li key={s.key}>
              <button className={board?.board_id === s.board_id ? 'on' : ''}
                      onClick={() => setBoard({ board_id: s.board_id, name: s.name })}>
                <strong>{s.name}</strong>
                <span>{s.blurb}</span>
              </button>
            </li>
          ))}
        </ul>
        <label className="upload">
          <input type="file" accept=".kicad_pcb" onChange={(e) => e.target.files[0] && onUpload(e.target.files[0])} />
          <span>Upload a .kicad_pcb — or drop one anywhere</span>
        </label>

        <h2>Settings</h2>
        {schema && settings && (
          <div className="fields">
            {schema.fields.map((f) => (
              <div className="field" key={f.name} title={f.help}>
                <label htmlFor={f.name}>{f.label}</label>
                {f.type === 'number' && (
                  <div className="row">
                    <input id={f.name} type="range" min={f.min} max={f.max} step={f.step}
                           value={settings[f.name]} onChange={(e) => set(f.name, Number(e.target.value))} />
                    <output>{settings[f.name]}{f.unit}</output>
                  </div>
                )}
                {f.type === 'choice' && (
                  <select id={f.name} value={settings[f.name]} onChange={(e) => set(f.name, e.target.value)}>
                    {f.choices.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                )}
                {f.type === 'bool' && (
                  <input id={f.name} type="checkbox" checked={!!settings[f.name]}
                         onChange={(e) => set(f.name, e.target.checked)} />
                )}
              </div>
            ))}
            <button className="reset" onClick={() => setSettings(schema.defaults)}>Reset to defaults</button>
          </div>
        )}
      </aside>

      <main>
        <div className="tabs">
          <button className={tab === '3d' ? 'on' : ''} onClick={() => setTab('3d')}>3D board</button>
          <button className={tab === '2d' ? 'on' : ''} onClick={() => setTab('2d')}>Top view</button>
          {result && <a className="share" onClick={() => navigator.clipboard?.writeText(location.href)}>Copy link</a>}
        </div>
        {error && <div className="error">{error}</div>}
        {tab === '3d' ? (
          <Viewer
            jobUrl={result ? fileUrl(result.job_id, 'board.stl') : null}
            zSplit={result ? result.recipe.base_thickness : 2}
            focus={focus}
          />
        ) : (
          <div className="preview">
            {result && <img src={fileUrl(result.job_id, 'preview.png')} alt="top view of the converted board" />}
          </div>
        )}
      </main>

      <aside className="right">
        <h2>Conversion</h2>
        <ol className="stages">
          {STEP_ORDER.map((name, i) => {
            const s = stages.find((x) => x.name === name)
            return (
              <li key={name} className={s ? 'done' : busy && stages.length === i ? 'running' : ''}>
                <span className="tick">{s ? '✓' : busy && stages.length === i ? '…' : ''}</span>
                <div>
                  <strong>{s ? s.label : ['Read the KiCad file', 'Turn it into 2D shapes', 'Apply the settings',
                                          'Build the 3D board', 'Write the files'][i]}</strong>
                  {s && <span>{s.detail} · {s.seconds}s</span>}
                </div>
              </li>
            )
          })}
        </ol>

        {result && done && (
          <>
            <h2>Result</h2>
            <dl className="stats">
              <div><dt>Board</dt><dd>{result.outline.size_mm[0]} × {result.outline.size_mm[1]} mm</dd></div>
              <div><dt>Copper</dt><dd>{b.copper_area_mm2.toFixed(0)} mm²</dd></div>
              <div><dt>Volume</dt><dd>{b.volume_mm3.toFixed(0)} mm³</dd></div>
              <div><dt>Holes</dt><dd>{result.summary.drills.total}
                {b.recipe_effects.drills_enlarged ? ` (+${b.recipe_effects.drills_enlarged} enlarged)` : ''}</dd></div>
              <div><dt>Pin holes</dt><dd>{b.recipe_effects.alignment_holes.length}</dd></div>
              <div><dt>Closed mesh</dt><dd>{b.watertight ? 'yes' : 'no'}</dd></div>
            </dl>

            <h2>Warnings {result.warnings.length > 0 && <em>({result.warnings.length})</em>}</h2>
            {result.warnings.length === 0 && <p className="ok">Nothing to report.</p>}
            <ul className="warnings">
              {result.warnings.map((w, i) => {
                const marker = result.markers.find((m) => m.message === w)
                return (
                  <li key={i} className={marker ? 'clickable' : ''}
                      onClick={() => marker && (setTab('3d'), setFocus(marker))}>
                    {w}{marker && <em> — show me</em>}
                  </li>
                )
              })}
            </ul>

            <h2>Download</h2>
            <div className="downloads">
              <a href={fileUrl(result.job_id, 'board.stl')}>board.stl</a>
              <a href={fileUrl(result.job_id, 'board.3mf')}>board.3mf</a>
              <a href={fileUrl(result.job_id, 'plot_1to1.pdf')}>1:1 PDF</a>
              <a href={fileUrl(result.job_id, 'report.json')}>report.json</a>
              <a href={bundleUrl(result.job_id)}>everything (.zip)</a>
            </div>
            <p className="tip">Open the 3MF in your slicer. The board prints flat, copper side up.</p>
          </>
        )}
      </aside>
    </div>
  )
}
