import { loadReport, sendJson } from '../_lib.js'

export default function handler(req, res) {
  const chapter = parseInt(req.query.chapter, 10)
  const report = loadReport(chapter)
  if (report === null) {
    sendJson(res, 404, { detail: `No report for chapter ${chapter}` })
    return
  }
  sendJson(res, 200, report)
}
