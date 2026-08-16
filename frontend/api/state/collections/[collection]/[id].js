import { loadState, COLLECTION_KEYS, sendJson } from '../../../_lib.js'

export default function handler(req, res) {
  const { collection, id } = req.query
  if (!COLLECTION_KEYS.has(collection)) {
    sendJson(res, 404, { detail: `Unknown collection: ${collection}` })
    return
  }
  const data = loadState()
  const raw = data[collection] || {}
  const fields = raw[id]
  if (fields === undefined) {
    sendJson(res, 404, { detail: `${collection}/${id} not found` })
    return
  }
  sendJson(res, 200, { id, fields })
}
