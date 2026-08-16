import { loadState, sendJson } from './_lib.js'

export default function handler(req, res) {
  const data = loadState()
  sendJson(res, 200, { evidence: data.evidence_store || {} })
}
