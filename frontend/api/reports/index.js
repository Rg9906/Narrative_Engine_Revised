import { listReports, sendJson } from '../_lib.js'

export default function handler(req, res) {
  sendJson(res, 200, { reports: listReports() })
}
