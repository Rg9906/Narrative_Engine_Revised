import { sendJson } from './_lib.js'

// This is a read-only static demo (frozen data snapshot, no live NLP pipeline
// or writable disk in a serverless environment) -- chapter ingestion is
// intentionally not implemented. The frontend already handles this failure
// gracefully (IngestPage shows a toast and stays on the upload form).
export default function handler(req, res) {
  sendJson(res, 501, {
    detail:
      'Chapter ingestion is disabled in this read-only demo deployment. ' +
      'Run the full app locally (see README) to process real chapters.',
  })
}
