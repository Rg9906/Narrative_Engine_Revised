import { motion } from 'framer-motion'
import type { StateSnapshot } from '@/types/state'
import { formatChapter, formatDate } from '@/lib/utils'
import { ConfidenceMeter } from '@/components/ui/ConfidenceMeter'
import { EvidenceList } from '@/components/state/EvidenceList'

interface FieldHistoryProps {
  current: StateSnapshot | null
  history: StateSnapshot[]
}

function renderValue(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (Array.isArray(value)) return value.join(', ')
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

export function FieldHistory({ current, history }: FieldHistoryProps) {
  const trajectory = [...history, ...(current ? [current] : [])]
  if (trajectory.length === 0) return null

  return (
    <ol className="relative ml-1.5 flex flex-col gap-4 border-l border-border pl-5">
      {trajectory.map((snapshot, i) => {
        const isCurrent = i === trajectory.length - 1
        return (
          <motion.li
            key={`${snapshot.chapter}-${snapshot.timestamp}-${i}`}
            initial={{ opacity: 0, x: -6 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.2, delay: i * 0.04 }}
            className="relative"
          >
            <span
              className={
                'absolute -left-[1.65rem] top-1 h-2.5 w-2.5 rounded-full ring-4 ring-surface ' +
                (isCurrent ? 'bg-primary' : 'bg-border-strong')
              }
            />
            <div className="flex flex-wrap items-center gap-2">
              <span className={isCurrent ? 'text-sm font-semibold text-foreground' : 'text-sm text-foreground'}>
                {renderValue(snapshot.value)}
              </span>
              <span className="text-xs text-muted-foreground">{formatChapter(snapshot.chapter)}</span>
              {isCurrent && (
                <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-primary">
                  current
                </span>
              )}
            </div>
            {snapshot.reasoning && (
              <p className="mt-0.5 text-xs text-muted-foreground">{snapshot.reasoning}</p>
            )}
            <div className="mt-1.5 flex items-center gap-3">
              <ConfidenceMeter value={snapshot.confidence} />
              <span className="text-[11px] text-muted-foreground/80">{formatDate(snapshot.timestamp)}</span>
            </div>
            <EvidenceList evidenceIds={snapshot.evidence_ids} className="mt-1.5" />
          </motion.li>
        )
      })}
    </ol>
  )
}
