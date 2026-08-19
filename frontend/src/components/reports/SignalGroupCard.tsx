import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import type { SignalGroup } from '@/types/state'
import { Badge } from '@/components/ui/Badge'
import { cn } from '@/lib/utils'

const SEVERITY_VARIANT: Record<string, 'destructive' | 'warning' | 'accent' | 'default'> = {
  error: 'destructive',
  warning: 'warning',
  suggestion: 'accent',
  note: 'default',
}

/** One deduplicated rule-based observation, however many entities tripped it.
 *
 * `count` is shown but deliberately does not drive prominence: fifty identical notes are
 * one rule firing fifty times, and are more often a miscalibrated detector than fifty
 * separate story problems. */
export function SignalGroupCard({ signal }: { signal: SignalGroup }) {
  const [open, setOpen] = useState(false)
  const Chevron = open ? ChevronDown : ChevronRight

  return (
    <div
      className={cn(
        'rounded-lg border bg-surface',
        signal.likely_detector_noise ? 'border-dashed border-border' : 'border-border',
      )}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-start gap-2 p-3 text-left"
      >
        <Chevron className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
        <div className="flex min-w-0 flex-1 flex-col gap-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium text-foreground">{signal.title}</span>
            <Badge variant={SEVERITY_VARIANT[signal.severity] ?? 'default'}>{signal.severity}</Badge>
            <Badge variant="outline">{signal.category}</Badge>
            {signal.count > 1 && (
              <span className="text-[11px] text-muted-foreground">fired {signal.count}×</span>
            )}
          </div>
          {signal.likely_detector_noise && (
            <span className="text-[11px] text-warning">
              Fired on {signal.count} entities — likely one over-eager rule rather than {signal.count}{' '}
              separate problems.
            </span>
          )}
        </div>
      </button>

      {open && (
        <div className="flex flex-col gap-2 border-t border-border px-3 py-2.5 pl-9">
          {signal.examples.map((example, i) => (
            <p key={i} className="text-xs text-muted-foreground">
              {example}
            </p>
          ))}
          {signal.suppressed_count > 0 && (
            <p className="text-[11px] italic text-muted-foreground">
              +{signal.suppressed_count} further instance{signal.suppressed_count === 1 ? '' : 's'} not shown
            </p>
          )}
          {signal.related_entities.length > 0 && (
            <div className="flex flex-wrap gap-1 pt-0.5">
              {signal.related_entities.slice(0, 20).map((e) => (
                <span
                  key={e}
                  className="rounded-full bg-muted px-2 py-0.5 font-mono text-[11px] text-muted-foreground"
                >
                  {e}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
