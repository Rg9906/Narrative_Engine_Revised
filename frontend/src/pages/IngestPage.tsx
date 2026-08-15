import { useState } from 'react'
import { toast } from 'sonner'
import { useQueryClient } from '@tanstack/react-query'
import { History } from 'lucide-react'
import { api } from '@/lib/api'
import { useIngestJob, useIngestJobs } from '@/lib/queries'
import { Dropzone } from '@/components/ingest/Dropzone'
import { JobProgress } from '@/components/ingest/JobProgress'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
import { formatDate } from '@/lib/utils'
import type { IngestJob } from '@/types/state'

const STATUS_BADGE: Record<IngestJob['status'], { variant: 'default' | 'success' | 'destructive' | 'warning'; label: string }> = {
  pending: { variant: 'warning', label: 'pending' },
  running: { variant: 'warning', label: 'running' },
  done: { variant: 'success', label: 'done' },
  error: { variant: 'destructive', label: 'error' },
}

export function IngestPage() {
  const [file, setFile] = useState<File | null>(null)
  const [jobId, setJobId] = useState<string | undefined>(undefined)
  const [uploading, setUploading] = useState(false)
  const queryClient = useQueryClient()

  const { data: job } = useIngestJob(jobId, { pollWhileActive: true })
  const { data: jobsData } = useIngestJobs()

  const handleUpload = async () => {
    if (!file) return
    setUploading(true)
    try {
      const { job_id } = await api.ingest(file)
      setJobId(job_id)
    } catch (err) {
      toast.error('Upload failed', { description: err instanceof Error ? err.message : String(err) })
    } finally {
      setUploading(false)
    }
  }

  const reset = () => {
    setFile(null)
    setJobId(undefined)
    queryClient.invalidateQueries({ queryKey: ['state'] })
    queryClient.invalidateQueries({ queryKey: ['reports'] })
  }

  const isBusy = uploading || job?.status === 'pending' || job?.status === 'running'
  const otherJobs = (jobsData?.jobs ?? []).filter((j) => j.id !== jobId)

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-1">
        <h2 className="text-xl font-semibold tracking-tight text-foreground">Ingest Chapter</h2>
        <p className="text-sm text-muted-foreground">
          Runs the full pipeline: NLP evidence extraction → narrative state delta → editorial review.
        </p>
      </div>

      {!job || job.status === 'error' ? (
        <div className="flex flex-col gap-4">
          <Dropzone onFileSelected={setFile} selectedFile={file} disabled={isBusy} />
          <Button onClick={handleUpload} disabled={!file || isBusy} className="w-fit">
            {uploading ? 'Uploading…' : 'Process chapter'}
          </Button>
          {job?.status === 'error' && <JobProgress job={job} onReset={reset} />}
        </div>
      ) : (
        <JobProgress job={job} onReset={reset} />
      )}

      {otherJobs.length > 0 && (
        <div className="flex flex-col gap-2.5">
          <div className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
            <History className="h-4 w-4 text-muted-foreground" />
            Recent jobs
          </div>
          <div className="flex flex-col gap-2">
            {otherJobs.map((j) => (
              <Card key={j.id} className="p-0">
                <button
                  onClick={() => {
                    setFile(null)
                    setJobId(j.id)
                  }}
                  disabled={isBusy}
                  className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/50 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-foreground">{j.filename}</p>
                    <p className="text-xs text-muted-foreground">
                      {formatDate(j.created_at)}
                      {j.result ? ` · Ch. ${j.result.chapter_number} · ${j.result.finding_count} findings` : ''}
                    </p>
                  </div>
                  <Badge variant={STATUS_BADGE[j.status].variant} className="shrink-0">
                    {STATUS_BADGE[j.status].label}
                  </Badge>
                </button>
              </Card>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
