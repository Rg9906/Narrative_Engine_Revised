import { useState } from 'react'
import { ChevronDown } from 'lucide-react'
import type { StateEntryField } from '@/types/state'
import { fieldLabel } from '@/lib/entityDisplay'
import { cn, formatChapter } from '@/lib/utils'
import { ConfidenceMeter } from '@/components/ui/ConfidenceMeter'
import { FieldHistory } from '@/components/state/FieldHistory'
import { EvidenceList } from '@/components/state/EvidenceList'

function renderValue(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (Array.isArray(value)) return value.length ? value.join(', ') : '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

export function FieldCard({ field }: { field: StateEntryField }) {
  const [open, setOpen] = useState(false)
  const hasHistory = field.history.length > 0

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {fieldLabel(field.key)}
          </p>
          <p className="mt-1 break-words text-sm font-medium text-foreground">
            {renderValue(field.current?.value)}
          </p>
        </div>
        {hasHistory && (
          <button
            onClick={() => setOpen((o) => !o)}
            className="flex shrink-0 items-center gap-1 rounded-md px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            aria-expanded={open}
          >
            {field.history.length + 1} versions
            <ChevronDown className={cn('h-3.5 w-3.5 transition-transform duration-200', open && 'rotate-180')} />
          </button>
        )}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
        {field.current && <ConfidenceMeter value={field.current.confidence} />}
        <span>Since {formatChapter(field.last_mentioned_chapter)}</span>
        <span>Importance {Math.round(field.importance * 100)}%</span>
      </div>

      {field.current?.reasoning && (
        <p className="mt-2 text-xs text-muted-foreground/90">{field.current.reasoning}</p>
      )}

      {field.current && <EvidenceList evidenceIds={field.current.evidence_ids} className="mt-2" />}

      {open && hasHistory && (
        <div className="mt-4 border-t border-border pt-4">
          <FieldHistory current={field.current} history={field.history} />
        </div>
      )}
    </div>
  )
}
