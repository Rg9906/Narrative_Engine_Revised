import { loadState, COLLECTION_KEYS, sendJson } from '../../_lib.js'

export default function handler(req, res) {
  const { collection } = req.query
  if (!COLLECTION_KEYS.has(collection)) {
    sendJson(res, 404, { detail: `Unknown collection: ${collection}` })
    return
  }
  const data = loadState()
  const raw = data[collection] || {}
  const entities = Object.entries(raw).map(([id, fields]) => ({ id, fields }))
  sendJson(res, 200, { collection, entities })
}
