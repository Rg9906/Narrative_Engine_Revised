import { loadState, sendJson } from '../_lib.js'

export default function handler(req, res) {
  const data = loadState()
  const timeline = data.timeline || []
  const sorted = [...timeline].sort((a, b) => (a.chapter || 0) - (b.chapter || 0))
  sendJson(res, 200, { events: sorted })
}
