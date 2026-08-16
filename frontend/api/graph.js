import { loadGraph, sendJson } from './_lib.js'

export default function handler(req, res) {
  sendJson(res, 200, loadGraph())
}
