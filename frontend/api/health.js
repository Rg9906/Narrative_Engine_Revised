import { sendJson } from './_lib.js'

export default function handler(req, res) {
  sendJson(res, 200, { status: 'ok' })
}
