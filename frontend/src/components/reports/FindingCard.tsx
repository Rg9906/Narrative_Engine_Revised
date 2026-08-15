import { AlertTriangle, Info, Lightbulb, ShieldAlert, XCircle } from 'lucide-react'
import type { Finding } from '@/types/state'
import { Badge } from '@/components/ui/Badge'
import { ConfidenceMeter } from '@/components/ui/ConfidenceMeter'
import { cn } from '@/lib/utils'

const SEVERITY_CONFIG: Record<string, { icon: typeof Info; variant: 'destructive' | 'warning' | 'accent' | 'default'; tone: string }> = {
  error: { icon: XCircle, variant: 'destructive', tone: 'text-destructive' },
  warning: { icon: AlertTriangle, variant: 'warning', tone: 'text-warning' },
  suggestion: { icon: Lightbulb, variant: 'accent', tone: 'text-accent' },
  note: { icon: Info, variant: 'default', tone: 'text-muted-foreground' },
  validation: { icon: ShieldAlert, variant: 'default', tone: 'text-muted-foreground' },
}

export function FindingCard({ finding }: { finding: Finding }) {
  const config = SEVERITY_CONFIG[finding.severity.toLowerCase()] ?? SEVERITY_CONFIG.note
  const Icon = config.icon

  return (
    <div className="flex gap-3 rounded-lg border border-border bg-surface p-4">
      <div className={cn('mt-0.5 shrink-0', config.tone)}>
        <Icon className="h-4 w-4" />
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-sm font-semibold text-foreground">{finding.title}</p>
          <Badge variant={config.variant}>{finding.category}</Badge>
        </div>
        <p className="text-sm text-muted-foreground">{finding.description}</p>
        <div className="mt-1 flex flex-wrap items-center gap-3">
          <ConfidenceMeter value={finding.confidence} />
          {finding.related_entities.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {finding.related_entities.map((e) => (
                <span key={e} className="rounded-full bg-muted px-2 py-0.5 font-mono text-[11px] text-muted-foreground">
                  {e}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
