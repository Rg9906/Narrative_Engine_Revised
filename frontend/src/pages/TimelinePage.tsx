import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Clock } from 'lucide-react'
import { useTimeline } from '@/lib/queries'
import { Skeleton } from '@/components/ui/Skeleton'
import { ErrorState } from '@/components/ui/ErrorState'
import { EmptyState } from '@/components/ui/EmptyState'
import { Input } from '@/components/ui/Input'
import { formatChapter } from '@/lib/utils'

export function TimelinePage() {
  const { data, isLoading, isError, error, refetch } = useTimeline()
  const [query, setQuery] = useState('')

  const grouped = useMemo(() => {
    const events = data?.events ?? []
    const filtered = query.trim()
      ? events.filter((e) =>
          [e.subject, e.predicate, e.object].filter(Boolean).join(' ').toLowerCase().includes(query.toLowerCase()),
        )
      : events

    const byChapter = new Map<number, typeof events>()
    for (const event of filtered) {
      const chapter = event.chapter ?? 0
      if (!byChapter.has(chapter)) byChapter.set(chapter, [])
      byChapter.get(chapter)!.push(event)
    }
    return [...byChapter.entries()].sort((a, b) => a[0] - b[0])
  }, [data, query])

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-1">
        <h2 className="text-xl font-semibold tracking-tight text-foreground">Timeline</h2>
        <p className="text-sm text-muted-foreground">
          Every subject-verb-object triple the deterministic pipeline extracted, grouped by chapter — the raw
          evidence feed the editorial inspectors reason over, not a curated summary. For a human-readable rundown
          of what actually happened in a chapter, see that chapter's{' '}
          <Link to="/reports" className="text-primary underline-offset-2 hover:underline">
            editorial report
          </Link>
          's "Key events" section.
        </p>
      </div>

      <Input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search events..."
        className="max-w-sm"
      />

      {isLoading && (
        <div className="flex flex-col gap-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </div>
      )}

      {isError && <ErrorState message={(error as Error)?.message ?? 'Failed to load timeline.'} onRetry={() => refetch()} />}

      {!isLoading && !isError && grouped.length === 0 && (
        <EmptyState icon={<Clock className="h-5 w-5" />} title="No events yet" description="Timeline events appear once a chapter has been ingested." />
      )}

      {!isLoading && !isError && grouped.length > 0 && (
        <div className="flex flex-col gap-6">
          {grouped.map(([chapter, events]) => (
            <div key={chapter} className="flex flex-col gap-2">
              <div className="sticky top-14 z-10 -mx-1 bg-background/90 px-1 py-1 backdrop-blur-sm">
                <span className="inline-flex items-center rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">
                  {formatChapter(chapter)} · {events.length} event{events.length === 1 ? '' : 's'}
                </span>
              </div>
              <ol className="ml-1.5 flex flex-col gap-2 border-l border-border pl-5">
                {events.map((event, i) => (
                  <motion.li
                    key={i}
                    initial={{ opacity: 0, x: -4 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.2, delay: Math.min(i * 0.02, 0.2) }}
                    className="relative text-sm text-foreground"
                  >
                    <span className="absolute -left-[1.65rem] top-1.5 h-2 w-2 rounded-full bg-border-strong" />
                    <span className="font-medium">{event.subject}</span>{' '}
                    <span className="text-muted-foreground">{event.predicate}</span>{' '}
                    <span>{event.object}</span>
                  </motion.li>
                ))}
              </ol>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
