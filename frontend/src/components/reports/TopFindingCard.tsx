import { AlertTriangle, ArrowRight, Info, Lightbulb, XCircle } from 'lucide-react'
import type { TopFinding } from '@/types/state'
import { Badge } from '@/components/ui/Badge'
import { ConfidenceMeter } from '@/components/ui/ConfidenceMeter'
import { cn } from '@/lib/utils'

const SEVERITY_CONFIG: Record<
  string,
  { icon: typeof Info; variant: 'destructive' | 'warning' | 'accent' | 'default'; tone: string }
> = {
  error: { icon: XCircle, variant: 'destructive', tone: 'text-destructive' },
  warning: { icon: AlertTriangle, variant: 'warning', tone: 'text-warning' },
  suggestion: { icon: Lightbulb, variant: 'accent', tone: 'text-accent' },
  note: { icon: Info, variant: 'default', tone: 'text-muted-foreground' },
}

/** A finding the synthesis pass promoted: it survived verification against the chapter,
 * was ranked against everything else the review found, and carries the consequence and a
 * concrete fix rather than only the observation. */
export function TopFindingCard({ finding }: { finding: TopFinding }) {
  const config = SEVERITY_CONFIG[(finding.severity ?? 'note').toLowerCase()] ?? SEVERITY_CONFIG.note
  const Icon = config.icon

  return (
    <div className="flex gap-3 rounded-lg border border-border bg-surface p-4">
      <div className="flex shrink-0 flex-col items-center gap-1.5">
        {finding.rank !== undefined && (
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-muted text-xs font-semibold text-muted-foreground">
            {finding.rank}
          </span>
        )}
        <Icon className={cn('h-4 w-4', config.tone)} />
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-sm font-semibold text-foreground">{finding.title}</p>
          <Badge variant={config.variant}>{finding.category}</Badge>
        </div>

        <p className="text-sm text-muted-foreground">{finding.description}</p>

        {finding.why_it_matters && (
          <p className="text-sm text-muted-foreground">
            <span className="font-medium text-foreground">Why it matters: </span>
            {finding.why_it_matters}
          </p>
        )}

        {finding.recommendation && (
          <p className="flex gap-1.5 rounded-md bg-muted/60 p-2.5 text-sm text-foreground">
            <ArrowRight className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
            <span>{finding.recommendation}</span>
          </p>
        )}

        <div className="mt-0.5 flex flex-wrap items-center gap-3">
          {typeof finding.confidence === 'number' && <ConfidenceMeter value={finding.confidence} />}
          {(finding.related_entities?.length ?? 0) > 0 && (
            <div className="flex flex-wrap gap-1">
              {finding.related_entities.map((e) => (
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

        {(finding.subsumes?.length ?? 0) > 0 && (
          <p className="text-[11px] text-muted-foreground">
            Covers rule-based signal{finding.subsumes!.length === 1 ? '' : 's'}:{' '}
            {finding.subsumes!.join(' · ')}
          </p>
        )}
      </div>
    </div>
  )
}
