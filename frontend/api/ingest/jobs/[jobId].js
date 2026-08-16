import { sendJson } from '../../_lib.js'

export default function handler(req, res) {
  sendJson(res, 404, { detail: 'Unknown job id' })
}
