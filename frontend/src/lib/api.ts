import type {
  CollectionName,
  Entity,
  Evidence,
  GraphData,
  IngestJob,
  ReportDetail,
  ReportSummary,
  StateSummary,
  TimelineResponse,
} from '@/types/state'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
    this.name = 'ApiError'
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, init)
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail ?? detail
    } catch {
      // response wasn't JSON; fall back to statusText
    }
    throw new ApiError(res.status, detail)
  }
  return res.json() as Promise<T>
}

export const api = {
  health: () => request<{ status: string }>('/health'),

  stateSummary: () => request<StateSummary>('/state/summary'),

  timeline: () => request<TimelineResponse>('/state/timeline'),

  collection: (name: CollectionName) =>
    request<{ collection: string; entities: Entity[] }>(`/state/collections/${name}`),

  entity: (name: CollectionName, id: string) =>
    request<Entity>(`/state/collections/${name}/${encodeURIComponent(id)}`),

  graph: () => request<GraphData>('/graph'),

  evidence: () => request<{ evidence: Record<string, Evidence> }>('/evidence'),

  reports: () => request<{ reports: ReportSummary[] }>('/reports'),

  report: (chapter: number) => request<ReportDetail>(`/reports/${chapter}`),

  ingest: async (file: File): Promise<{ job_id: string }> => {
    const form = new FormData()
    form.append('file', file)
    const res = await fetch('/api/ingest', { method: 'POST', body: form })
    if (!res.ok) {
      let detail = res.statusText
      try {
        const body = await res.json()
        detail = body.detail ?? detail
      } catch {
        // ignore
      }
      throw new ApiError(res.status, detail)
    }
    return res.json()
  },

  ingestJob: (jobId: string) => request<IngestJob>(`/ingest/jobs/${jobId}`),

  ingestJobs: () => request<{ jobs: IngestJob[] }>('/ingest/jobs'),
}
