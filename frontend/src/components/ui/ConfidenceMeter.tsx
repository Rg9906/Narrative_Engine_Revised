import { cn, clampPercent } from '@/lib/utils'

interface ConfidenceMeterProps {
  value: number // 0..1
  className?: string
  showLabel?: boolean
}

function toneFor(pct: number): string {
  if (pct >= 75) return 'bg-success'
  if (pct >= 45) return 'bg-warning'
  return 'bg-destructive'
}

export function ConfidenceMeter({ value, className, showLabel = true }: ConfidenceMeterProps) {
  const pct = clampPercent(Math.round(value * 100))
  return (
    <div className={cn('flex items-center gap-2', className)}>
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-muted">
        <div
          className={cn('h-full rounded-full transition-all duration-500 ease-out', toneFor(pct))}
          style={{ width: `${pct}%` }}
        />
      </div>
      {showLabel ? (
        <span className="font-mono text-xs tabular-nums text-muted-foreground">{pct}%</span>
      ) : null}
    </div>
  )
}
