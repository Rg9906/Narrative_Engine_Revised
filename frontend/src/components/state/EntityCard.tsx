import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ChevronRight } from 'lucide-react'
import type { Entity } from '@/types/state'
import { getPrimaryLabel, getSummaryChips, statusTone, fieldLabel, getLastMentionedChapter } from '@/lib/entityDisplay'
import { Badge } from '@/components/ui/Badge'
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/Tooltip'
import { formatChapter } from '@/lib/utils'

interface EntityCardProps {
  entity: Entity
  collection: string
  to: string
  index?: number
}

export function EntityCard({ entity, collection, to, index = 0 }: EntityCardProps) {
  const label = getPrimaryLabel(collection, entity)
  const chips = getSummaryChips(entity)
  const lastChapter = getLastMentionedChapter(entity)

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, delay: Math.min(index * 0.03, 0.3), ease: 'easeOut' }}
    >
      <Link
        to={to}
        className="group flex flex-col gap-3 rounded-xl border border-border bg-surface p-4 shadow-soft transition-all duration-150 hover:-translate-y-0.5 hover:border-border-strong hover:shadow-elevated"
      >
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <Tooltip>
              <TooltipTrigger asChild>
                <p className="truncate text-sm font-semibold text-foreground">{label}</p>
              </TooltipTrigger>
              <TooltipContent>{label}</TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <p className="truncate font-mono text-xs text-muted-foreground">{entity.id}</p>
              </TooltipTrigger>
              <TooltipContent>{entity.id}</TooltipContent>
            </Tooltip>
          </div>
          <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-150 group-hover:translate-x-0.5 group-hover:text-foreground" />
        </div>

        {chips.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {chips.map((chip) =>
              chip.key === 'status' ? (
                <Badge key={chip.key} variant={statusTone(chip.value)}>
                  {chip.value}
                </Badge>
              ) : (
                <Badge key={chip.key} variant="outline">
                  {fieldLabel(chip.key)}: {chip.value}
                </Badge>
              ),
            )}
          </div>
        )}

        <div className="mt-auto flex items-center justify-between text-xs text-muted-foreground">
          <span>{Object.keys(entity.fields).length} tracked field{Object.keys(entity.fields).length === 1 ? '' : 's'}</span>
          <span>Last seen {formatChapter(lastChapter)}</span>
        </div>
      </Link>
    </motion.div>
  )
}
