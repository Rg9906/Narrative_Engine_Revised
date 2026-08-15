import { useState } from 'react'
import { ChevronDown, Quote } from 'lucide-react'
import { motion } from 'framer-motion'
import { useEvidence } from '@/lib/queries'
import { ConfidenceMeter } from '@/components/ui/ConfidenceMeter'
import { Badge } from '@/components/ui/Badge'
import { cn, formatChapter, formatDate } from '@/lib/utils'

const EVIDENCE_TYPE_TONE: Record<string, 'default' | 'accent' | 'success'> = {
  DIRECT_STATEMENT: 'success',
  DIALOGUE: 'accent',
  ACTION: 'default',
}

interface EvidenceListProps {
  evidenceIds: string[]
  className?: string
}

/** Expandable list of the raw evidence pieces backing a state snapshot's evidence_ids. */
export function EvidenceList({ evidenceIds, className }: EvidenceListProps) {
  const [open, setOpen] = useState(false)
  const { data, isLoading } = useEvidence()

  if (!evidenceIds || evidenceIds.length === 0) return null

  const pieces = evidenceIds.map((id) => data?.evidence[id]).filter((e): e is NonNullable<typeof e> => Boolean(e))

  return (
    <div className={className}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center gap-1 text-[11px] font-medium text-muted-foreground transition-colors hover:text-foreground"
        aria-expanded={open}
      >
        <Quote className="h-3 w-3" />
        {evidenceIds.length} source{evidenceIds.length === 1 ? '' : 's'}
        <ChevronDown className={cn('h-3 w-3 transition-transform duration-200', open && 'rotate-180')} />
      </button>

      {open && (
        <div className="mt-2 flex flex-col gap-1.5 border-l border-border pl-3">
          {isLoading && <p className="text-[11px] text-muted-foreground">Loading evidence...</p>}
          {!isLoading && pieces.length === 0 && (
            <p className="text-[11px] text-muted-foreground">
              Evidence ids recorded but not found in the current evidence store.
            </p>
          )}
          {pieces.map((piece, i) => (
            <motion.div
              key={piece.id}
              initial={{ opacity: 0, x: -4 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.15, delay: i * 0.03 }}
              className="rounded-md bg-muted/50 px-2.5 py-1.5"
            >
              <div className="flex flex-wrap items-center gap-1.5">
                <Badge variant={EVIDENCE_TYPE_TONE[piece.evidence_type] ?? 'default'} className="text-[10px]">
                  {piece.evidence_type.replace(/_/g, ' ').toLowerCase()}
                </Badge>
                <span className="text-[11px] text-muted-foreground">{formatChapter(piece.source_chapter)}</span>
                <ConfidenceMeter value={piece.confidence} className="ml-auto" />
              </div>
              <p className="mt-1 text-xs text-foreground">
                {piece.text_span ? `"${piece.text_span}"` : piece.interpretation_hint ?? 'No description recorded.'}
              </p>
              <p className="mt-0.5 text-[10px] text-muted-foreground/80">{formatDate(piece.timestamp)}</p>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  )
}
