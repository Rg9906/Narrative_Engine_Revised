import { loadState, buildSummary, sendJson } from '../_lib.js'

export default function handler(req, res) {
  const data = loadState()
  sendJson(res, 200, buildSummary(data))
}
