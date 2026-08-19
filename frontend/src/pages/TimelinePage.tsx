import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Clock, Database } from 'lucide-react'
import { useTimeline } from '@/lib/queries'
import type { RawRelation, TimelineEvent } from '@/types/state'
import { Skeleton } from '@/components/ui/Skeleton'
import { ErrorState } from '@/components/ui/ErrorState'
import { EmptyState } from '@/components/ui/EmptyState'
import { Input } from '@/components/ui/Input'
import { Badge } from '@/components/ui/Badge'
import { formatChapter } from '@/lib/utils'

/** Colour by what kind of beat it is, so a scan of the page reads as story shape. */
const EVENT_TYPE_STYLES: Record<string, string> = {
  revelation: 'bg-violet-500/10 text-violet-600 dark:text-violet-400',
  discovery: 'bg-violet-500/10 text-violet-600 dark:text-violet-400',
  decision: 'bg-blue-500/10 text-blue-600 dark:text-blue-400',
  conflict: 'bg-red-500/10 text-red-600 dark:text-red-400',
  betrayal: 'bg-red-500/10 text-red-600 dark:text-red-400',
  death: 'bg-red-600/15 text-red-700 dark:text-red-400',
  setback: 'bg-amber-500/10 text-amber-600 dark:text-amber-400',
  arrival: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
  departure: 'bg-slate-500/10 text-slate-600 dark:text-slate-400',
  reunion: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
  promise: 'bg-teal-500/10 text-teal-600 dark:text-teal-400',
}

function eventText(event: TimelineEvent): string {
  if (event.summary) return event.summary
  return [event.subject, event.predicate, event.object].filter(Boolean).join(' ')
}

function relationText(relation: RawRelation): string {
  return [relation.subject, relation.predicate, relation.object].filter(Boolean).join(' ')
}

function groupByChapter<T extends { chapter?: number }>(items: T[]): [number, T[]][] {
  const byChapter = new Map<number, T[]>()
  for (const item of items) {
    const chapter = item.chapter ?? 0
    if (!byChapter.has(chapter)) byChapter.set(chapter, [])
    byChapter.get(chapter)!.push(item)
  }
  return [...byChapter.entries()].sort((a, b) => a[0] - b[0])
}

export function TimelinePage() {
  const { data, isLoading, isError, error, refetch } = useTimeline()
  const [query, setQuery] = useState('')
  const [showRaw, setShowRaw] = useState(false)
  const [showStructural, setShowStructural] = useState(false)

  const events = data?.events ?? []
  const rawRelations = data?.raw_relations ?? []

  const groupedEvents = useMemo(() => {
    const needle = query.trim().toLowerCase()
    const visible = events.filter((event) => {
      // Structural markers (moves_to / acquires / discards) exist for the inspectors,
      // not for reading. Deaths are structural but genuinely story-level, so those are
      // flagged reader_facing and always shown.
      if (event.kind === 'structural' && !event.reader_facing && !showStructural) return false
      if (!needle) return true
      return eventText(event).toLowerCase().includes(needle)
    })
    return groupByChapter(visible)
  }, [events, query, showStructural])

  const groupedRaw = useMemo(() => {
    if (!showRaw) return []
    const needle = query.trim().toLowerCase()
    const visible = needle
      ? rawRelations.filter((relation) => relationText(relation).toLowerCase().includes(needle))
      : rawRelations
    return groupByChapter(visible)
  }, [rawRelations, query, showRaw])

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-1">
        <h2 className="text-xl font-semibold tracking-tight text-foreground">Timeline</h2>
        <p className="text-sm text-muted-foreground">
          The story's chronology: plot beats the engine judged load-bearing, with what each one
          changes. The {rawRelations.length.toLocaleString()} raw subject-verb-object triples the
          NLP layer extracted are evidence, not events — they're available below, off by default.
          For a chapter's full editorial write-up, see its{' '}
          <Link to="/reports" className="text-primary underline-offset-2 hover:underline">
            editorial report
          </Link>
          .
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search events..."
          className="max-w-sm"
        />
        <label className="flex cursor-pointer items-center gap-2 text-sm text-muted-foreground">
          <input
            type="checkbox"
            checked={showStructural}
            onChange={(e) => setShowStructural(e.target.checked)}
            className="h-3.5 w-3.5 rounded border-border"
          />
          Show derived markers
        </label>
        <label className="flex cursor-pointer items-center gap-2 text-sm text-muted-foreground">
          <input
            type="checkbox"
            checked={showRaw}
            onChange={(e) => setShowRaw(e.target.checked)}
            className="h-3.5 w-3.5 rounded border-border"
          />
          Show raw NLP evidence ({rawRelations.length.toLocaleString()})
        </label>
      </div>

      {isLoading && (
        <div className="flex flex-col gap-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </div>
      )}

      {isError && (
        <ErrorState message={(error as Error)?.message ?? 'Failed to load timeline.'} onRetry={() => refetch()} />
      )}

      {!isLoading && !isError && groupedEvents.length === 0 && (
        <EmptyState
          icon={<Clock className="h-5 w-5" />}
          title="No story beats yet"
          description={
            rawRelations.length > 0
              ? 'Raw evidence has been extracted, but no curated beats exist for it yet. Beats are authored by the LLM timeline stage during ingestion — reprocess a chapter with an LLM provider configured.'
              : 'Timeline events appear once a chapter has been ingested.'
          }
        />
      )}

      {!isLoading && !isError && groupedEvents.length > 0 && (
        <div className="flex flex-col gap-6">
          {groupedEvents.map(([chapter, chapterEvents]) => (
            <div key={chapter} className="flex flex-col gap-2">
              <div className="sticky top-14 z-10 -mx-1 bg-background/90 px-1 py-1 backdrop-blur-sm">
                <span className="inline-flex items-center rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">
                  {formatChapter(chapter)} · {chapterEvents.length} beat{chapterEvents.length === 1 ? '' : 's'}
                </span>
              </div>
              <ol className="ml-1.5 flex flex-col gap-3 border-l border-border pl-5">
                {chapterEvents.map((event, i) => {
                  const type = (event.event_type ?? '').toLowerCase()
                  const isStructural = event.kind === 'structural'
                  return (
                    <motion.li
                      key={i}
                      initial={{ opacity: 0, x: -4 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ duration: 0.2, delay: Math.min(i * 0.02, 0.2) }}
                      className="relative flex flex-col gap-1 text-sm text-foreground"
                    >
                      <span
                        className={`absolute -left-[1.65rem] top-1.5 h-2 w-2 rounded-full ${
                          isStructural ? 'bg-border-strong' : 'bg-primary'
                        }`}
                      />
                      <div className="flex flex-wrap items-center gap-2">
                        <span className={isStructural ? 'text-muted-foreground' : 'font-medium'}>
                          {eventText(event)}
                        </span>
                        {type && (
                          <span
                            className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${
                              EVENT_TYPE_STYLES[type] ?? 'bg-muted text-muted-foreground'
                            }`}
                          >
                            {type}
                          </span>
                        )}
                        {isStructural && <Badge variant="outline">derived</Badge>}
                        {typeof event.significance === 'number' && (
                          <span className="text-[11px] text-muted-foreground">
                            significance {event.significance.toFixed(2)}
                          </span>
                        )}
                      </div>
                      {event.why_it_matters && (
                        <span className="text-xs text-muted-foreground">{event.why_it_matters}</span>
                      )}
                      {(event.time || event.location || (event.participants?.length ?? 0) > 0) && (
                        <span className="text-[11px] text-muted-foreground">
                          {[
                            event.time ? `when: ${event.time}` : null,
                            event.location ? `where: ${event.location}` : null,
                            event.participants?.length ? `who: ${event.participants.join(', ')}` : null,
                          ]
                            .filter(Boolean)
                            .join(' · ')}
                        </span>
                      )}
                    </motion.li>
                  )
                })}
              </ol>
            </div>
          ))}
        </div>
      )}

      {showRaw && (
        <div className="flex flex-col gap-4 border-t border-border pt-5">
          <div className="flex flex-col gap-1">
            <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <Database className="h-4 w-4 text-muted-foreground" />
              Raw NLP evidence
            </h3>
            <p className="text-xs text-muted-foreground">
              Every dependency-parsed subject-verb-object triple, exactly as spaCy emitted it. One
              sentence commonly produces several rows, and description is indistinguishable from
              plot at this layer — which is why these are evidence for the inspectors rather than
              entries in the chronology above.
            </p>
          </div>
          {groupedRaw.map(([chapter, relations]) => (
            <div key={chapter} className="flex flex-col gap-1.5">
              <span className="text-xs font-semibold text-muted-foreground">
                {formatChapter(chapter)} · {relations.length} relation{relations.length === 1 ? '' : 's'}
              </span>
              <ul className="flex flex-col gap-0.5">
                {relations.map((relation, i) => (
                  <li key={i} className="font-mono text-xs text-muted-foreground">
                    {relationText(relation)}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
