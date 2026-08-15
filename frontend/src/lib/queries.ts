import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { CollectionName } from '@/types/state'

export function useStateSummary() {
  return useQuery({ queryKey: ['state', 'summary'], queryFn: api.stateSummary })
}

export function useTimeline() {
  return useQuery({ queryKey: ['state', 'timeline'], queryFn: api.timeline })
}

export function useCollection(name: CollectionName) {
  return useQuery({ queryKey: ['state', 'collection', name], queryFn: () => api.collection(name) })
}

export function useEntity(name: CollectionName, id: string | undefined) {
  return useQuery({
    queryKey: ['state', 'entity', name, id],
    queryFn: () => api.entity(name, id as string),
    enabled: Boolean(id),
  })
}

export function useGraph() {
  return useQuery({ queryKey: ['graph'], queryFn: api.graph })
}

export function useEvidence() {
  return useQuery({ queryKey: ['evidence'], queryFn: api.evidence, staleTime: 5 * 60 * 1000 })
}

export function useReports() {
  return useQuery({ queryKey: ['reports'], queryFn: api.reports })
}

export function useReport(chapter: number | undefined) {
  return useQuery({
    queryKey: ['reports', chapter],
    queryFn: () => api.report(chapter as number),
    enabled: chapter !== undefined,
  })
}

export function useIngestJobs() {
  return useQuery({
    queryKey: ['ingest', 'jobs'],
    queryFn: api.ingestJobs,
    refetchInterval: 5000,
  })
}

export function useIngestJob(jobId: string | undefined, opts?: { pollWhileActive?: boolean }) {
  return useQuery({
    queryKey: ['ingest', 'job', jobId],
    queryFn: () => api.ingestJob(jobId as string),
    enabled: Boolean(jobId),
    refetchInterval: (query) => {
      if (!opts?.pollWhileActive) return false
      const status = query.state.data?.status
      if (status === 'done' || status === 'error') return false
      return 1500
    },
  })
}
