import type { ReactNode } from 'react'
import { motion } from 'framer-motion'
import { cn } from '@/lib/utils'
import { AnimatedNumber } from '@/components/ui/AnimatedNumber'

interface StatTileProps {
  label: string
  value: number
  icon?: ReactNode
  hint?: string
  tone?: 'default' | 'success' | 'warning' | 'destructive' | 'accent'
  className?: string
}

const toneClasses: Record<NonNullable<StatTileProps['tone']>, string> = {
  default: 'text-primary bg-primary/10',
  success: 'text-success bg-success/10',
  warning: 'text-warning bg-warning/10',
  destructive: 'text-destructive bg-destructive/10',
  accent: 'text-accent bg-accent/10',
}

export function StatTile({ label, value, icon, hint, tone = 'default', className }: StatTileProps) {
  return (
    <motion.div
      whileHover={{ y: -2 }}
      transition={{ duration: 0.15 }}
      className={cn(
        'flex items-start justify-between gap-3 rounded-xl border border-border bg-surface p-5 shadow-soft',
        className,
      )}
    >
      <div className="flex flex-col gap-1">
        <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</span>
        <span className="text-2xl font-semibold tabular-nums text-foreground">
          <AnimatedNumber value={value} />
        </span>
        {hint ? <span className="text-xs text-muted-foreground">{hint}</span> : null}
      </div>
      {icon ? (
        <div className={cn('flex h-9 w-9 shrink-0 items-center justify-center rounded-lg', toneClasses[tone])}>
          {icon}
        </div>
      ) : null}
    </motion.div>
  )
}
