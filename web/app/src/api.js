// Every call the browser makes. The AI layer, when it lands, calls these same routes.
export const API = (import.meta.env.VITE_API_BASE || 'http://localhost:8765').replace(/\/$/, '')

const json = async (r) => {
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `${r.status} ${r.statusText}`)
  return r.json()
}

export const getSchema = () => fetch(`${API}/api/recipe/schema`).then(json)
export const getSamples = () => fetch(`${API}/api/samples`).then(json)

export const uploadBoard = (file) => {
  const body = new FormData()
  body.append('file', file)
  return fetch(`${API}/api/boards`, { method: 'POST', body }).then(json)
}

// Streams the conversion: onStage for each step, resolves with the finished result.
export function convertStream(boardId, settings, onStage) {
  const url = `${API}/api/convert/stream?board_id=${encodeURIComponent(boardId)}&settings=${encodeURIComponent(JSON.stringify(settings))}`
  const es = new EventSource(url)
  const done = new Promise((resolve, reject) => {
    es.addEventListener('stage', (e) => onStage(JSON.parse(e.data)))
    es.addEventListener('done', (e) => { es.close(); resolve(JSON.parse(e.data)) })
    es.addEventListener('error', (e) => {
      es.close()
      reject(new Error(e.data ? JSON.parse(e.data).detail : 'the conversion service is unreachable'))
    })
  })
  return { done, cancel: () => es.close() }
}

export const fileUrl = (jobId, name) => `${API}/api/jobs/${jobId}/files/${name}`
export const bundleUrl = (jobId) => `${API}/api/jobs/${jobId}/bundle.zip`
