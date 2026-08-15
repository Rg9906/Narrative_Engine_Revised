import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { CheckCircle2, Loader2, XCircle } from 'lucide-react'
import type { IngestJob } from '@/types/state'
import { Button } from '@/components/ui/Button'
import { Progress } from '@/components/ui/Progress'

const STAGES = [
  'Parsing chapter text',
  'Running NLP pipeline (spaCy, GLiNER, FastCoref)',
  'Computing narrative state delta',
  'Running editorial inspectors',
  'Persisting state & report',
]

function useElapsedSeconds(active: boolean) {
  const [seconds, setSeconds] = useState(0)
  useEffect(() => {
    if (!active) return
    const id = setInterval(() => setSeconds((s) => s + 1), 1000)
    return () => clearInterval(id)
  }, [active])
  return seconds
}

export function JobProgress({ job, onReset }: { job: IngestJob; onReset: () => void }) {
  const isActive = job.status === 'pending' || job.status === 'running'
  const elapsed = useElapsedSeconds(isActive)
  const stageIndex = Math.min(STAGES.length - 1, Math.floor(elapsed / 8))

  if (job.status === 'error') {
    return (
      <motion.div
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex flex-col gap-3 rounded-xl border border-destructive/30 bg-destructive/5 p-5"
      >
        <div className="flex items-center gap-2 text-destructive">
          <XCircle className="h-5 w-5" />
          <p className="text-sm font-semibold">Ingestion failed</p>
        </div>
        <p className="text-sm text-muted-foreground">{job.error?.message}</p>
        <Button variant="outline" size="sm" className="w-fit" onClick={onReset}>
          Try another file
        </Button>
      </motion.div>
    )
  }

  if (job.status === 'done' && job.result) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex flex-col gap-4 rounded-xl border border-success/30 bg-success/5 p-5"
      >
        <div className="flex items-center gap-2 text-success">
          <CheckCircle2 className="h-5 w-5" />
          <p className="text-sm font-semibold">Chapter {job.result.chapter_number} processed</p>
        </div>
        <p className="text-sm text-muted-foreground">{job.result.delta_summary}</p>
        <div className="grid grid-cols-3 gap-3 text-center">
          <div>
            <p className="text-lg font-semibold text-foreground">{job.result.change_count}</p>
            <p className="text-xs text-muted-foreground">state changes</p>
          </div>
          <div>
            <p className="text-lg font-semibold text-foreground">{job.result.finding_count}</p>
            <p className="text-xs text-muted-foreground">editorial findings</p>
          </div>
          <div>
            <p className="text-lg font-semibold text-foreground">{job.result.total_chapters_processed}</p>
            <p className="text-xs text-muted-foreground">chapters total</p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button asChild size="sm">
            <Link to={`/reports/${job.result.chapter_number}`}>View editorial report</Link>
          </Button>
          <Button variant="outline" size="sm" onClick={onReset}>
            Ingest another
          </Button>
        </div>
      </motion.div>
    )
  }

  return (
    <div className="flex flex-col gap-4 rounded-xl border border-border bg-surface p-5">
      <div className="flex items-center gap-2 text-primary">
        <Loader2 className="h-4 w-4 animate-spin" />
        <p className="text-sm font-semibold text-foreground">Processing {job.filename}…</p>
      </div>
      <Progress value={((stageIndex + 1) / STAGES.length) * 100} className="[&>div]:transition-[transform] [&>div]:duration-1000" />
      <ul className="flex flex-col gap-1.5">
        {STAGES.map((stage, i) => (
          <li
            key={stage}
            className={
              'text-xs transition-colors duration-300 ' +
              (i < stageIndex
                ? 'text-muted-foreground line-through'
                : i === stageIndex
                  ? 'font-medium text-foreground'
                  : 'text-muted-foreground/50')
            }
          >
            {stage}
          </li>
        ))}
      </ul>
      <p className="text-xs text-muted-foreground">
        {elapsed}s elapsed — first run per model can take longer while models load.
      </p>
    </div>
  )
}
