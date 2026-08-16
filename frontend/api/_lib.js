// Shared helpers for the static-demo API layer.
//
// This mirrors api/state_data.py, api/graph_data.py, and api/reports_data.py
// (the real Python/FastAPI backend) closely enough that frontend/src/lib/api.ts
// needs zero changes -- same routes, same response shapes. The difference is
// these read from a frozen JSON snapshot bundled at deploy time
// (frontend/api/_snapshot/) instead of a live NarrativeState, since Vercel's
// serverless model can't run the real Python NLP pipeline (spaCy/GLiNER/
// FastCoref are multi-GB and ingestion takes 60-90s per chapter, both
// incompatible with serverless function limits) or persist writes to disk.
//
// Read-only by design: POST /api/ingest is intentionally not implemented here.
//
// ESM, not CommonJS: frontend/package.json has "type": "module", so Node
// treats every .js file here as an ES module regardless of require()/
// module.exports -- using CommonJS syntax made every function fail at
// runtime with FUNCTION_INVOCATION_FAILED (confirmed via a real deploy).

import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const SNAPSHOT_DIR = path.join(__dirname, '_snapshot')

export const COLLECTION_KEYS = new Set([
  'characters', 'relationships', 'world', 'themes', 'motifs',
  'promises', 'threats', 'mysteries', 'conflicts', 'arcs', 'style',
])

let _stateCache = null
export function loadState() {
  if (_stateCache) return _stateCache
  const raw = fs.readFileSync(path.join(SNAPSHOT_DIR, 'narrative_state.json'), 'utf-8')
  _stateCache = JSON.parse(raw)
  return _stateCache
}

let _graphCache = null
export function loadGraph() {
  if (_graphCache) return _graphCache
  const raw = fs.readFileSync(path.join(SNAPSHOT_DIR, 'narrative_graph.json'), 'utf-8')
  _graphCache = JSON.parse(raw)
  return _graphCache
}

export function loadReport(chapter) {
  const file = path.join(SNAPSHOT_DIR, 'reports', `editorial_report_ch${chapter}.json`)
  if (!fs.existsSync(file)) return null
  return JSON.parse(fs.readFileSync(file, 'utf-8'))
}

export function listReports() {
  const dir = path.join(SNAPSHOT_DIR, 'reports')
  if (!fs.existsSync(dir)) return []
  const re = /^editorial_report_ch(\d+)\.json$/
  const summaries = []
  for (const name of fs.readdirSync(dir)) {
    const m = re.exec(name)
    if (!m) continue
    const report = JSON.parse(fs.readFileSync(path.join(dir, name), 'utf-8'))
    const findings = report.findings || []
    const severityCounts = {}
    for (const f of findings) {
      const sev = String(f.severity || 'note').toLowerCase()
      severityCounts[sev] = (severityCounts[sev] || 0) + 1
    }
    summaries.push({
      chapter: parseInt(m[1], 10),
      generated_at: report.metadata?.generated_at ?? null,
      inspector_count: report.metadata?.inspector_count ?? null,
      llm_provider: report.metadata?.llm_provider ?? null,
      finding_count: findings.length,
      severity_counts: severityCounts,
    })
  }
  summaries.sort((a, b) => b.chapter - a.chapter)
  return summaries
}

function currentValue(entry, fieldKey) {
  const field = (entry || {})[fieldKey]
  if (!field) return null
  const current = field.current
  if (!current) return null
  return current.value ?? null
}

export function buildSummary(data) {
  const counts = {}
  for (const key of COLLECTION_KEYS) counts[key] = Object.keys(data[key] || {}).length
  counts.timeline_events = (data.timeline || []).length
  counts.evidence = Object.keys(data.evidence_store || {}).length

  const timeline = data.timeline || []
  const recentTimeline = [...timeline]
    .sort((a, b) => (a.chapter || 0) - (b.chapter || 0))
    .slice(-8)
    .reverse()

  let openPromises = 0
  for (const entry of Object.values(data.promises || {})) {
    const status = currentValue(entry, 'status')
    if (status && String(status).toUpperCase() === 'OPEN') openPromises += 1
  }

  let unresolvedMysteries = 0
  for (const entry of Object.values(data.mysteries || {})) {
    const status = currentValue(entry, 'status')
    if (status && !['RESOLVED', 'FULFILLED', 'CLOSED'].includes(String(status).toUpperCase())) {
      unresolvedMysteries += 1
    }
  }

  return {
    metadata: data.metadata || {},
    counts,
    open_promises: openPromises,
    unresolved_mysteries: unresolvedMysteries,
    recent_timeline: recentTimeline,
  }
}

export function sendJson(res, status, body) {
  res.status(status).setHeader('Content-Type', 'application/json').send(JSON.stringify(body))
}
