import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  Users,
  Heart,
  Globe,
  Sparkles,
  ScrollText,
  BookOpen,
  FileWarning,
  UploadCloud,
  Clock,
  ArrowRight,
} from 'lucide-react'
import { useStateSummary } from '@/lib/queries'
import { StatTile } from '@/components/ui/StatTile'
import { Skeleton } from '@/components/ui/Skeleton'
import { ErrorState } from '@/components/ui/ErrorState'
import { EmptyState } from '@/components/ui/EmptyState'
import { Button } from '@/components/ui/Button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'

export function OverviewPage() {
  const { data, isLoading, isError, error, refetch } = useStateSummary()

  if (isLoading) {
    return (
      <div className="flex flex-col gap-5">
        <Skeleton className="h-8 w-72" />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
      </div>
    )
  }

  if (isError) {
    return <ErrorState message={(error as Error)?.message ?? 'Failed to load narrative state.'} onRetry={() => refetch()} />
  }

  const counts = data?.counts
  const hasAnyData = data && data.metadata.total_chapters_processed > 0

  if (!hasAnyData) {
    return (
      <div className="flex flex-col gap-6">
        <h2 className="text-xl font-semibold tracking-tight text-foreground">Overview</h2>
        <EmptyState
          icon={<BookOpen className="h-5 w-5" />}
          title="No chapters processed yet"
          description="Ingest your first chapter to start building the story's evolving memory — characters, relationships, world, themes, and promises will populate here."
          action={
            <Button asChild size="sm">
              <Link to="/ingest">
                <UploadCloud className="h-4 w-4" />
                Ingest a chapter
              </Link>
            </Button>
          }
        />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h2 className="text-xl font-semibold tracking-tight text-foreground">Overview</h2>
        <p className="text-sm text-muted-foreground">
          {data.metadata.total_chapters_processed} chapters processed · last updated{' '}
          {data.metadata.last_updated ? new Date(data.metadata.last_updated).toLocaleDateString() : '—'}
        </p>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile label="Characters" value={counts!.characters} icon={<Users className="h-4 w-4" />} />
        <StatTile label="Relationships" value={counts!.relationships} icon={<Heart className="h-4 w-4" />} tone="accent" />
        <StatTile label="World Elements" value={counts!.world} icon={<Globe className="h-4 w-4" />} tone="success" />
        <StatTile label="Themes & Motifs" value={counts!.themes + counts!.motifs} icon={<Sparkles className="h-4 w-4" />} tone="accent" />
        <StatTile
          label="Open Promises"
          value={data.open_promises}
          icon={<ScrollText className="h-4 w-4" />}
          tone={data.open_promises > 0 ? 'warning' : 'success'}
        />
        <StatTile
          label="Unresolved Mysteries"
          value={data.unresolved_mysteries}
          icon={<FileWarning className="h-4 w-4" />}
          tone={data.unresolved_mysteries > 0 ? 'warning' : 'success'}
        />
        <StatTile label="Timeline Events" value={counts!.timeline_events} icon={<Clock className="h-4 w-4" />} />
        <StatTile label="Evidence Pieces" value={counts!.evidence} icon={<BookOpen className="h-4 w-4" />} tone="default" />
      </div>

      <Card>
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <CardTitle>Recent timeline activity</CardTitle>
          <Button asChild variant="ghost" size="sm">
            <Link to="/timeline">
              View all
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </Button>
        </CardHeader>
        <CardContent>
          {data.recent_timeline.length === 0 ? (
            <p className="text-sm text-muted-foreground">No events recorded yet.</p>
          ) : (
            <ul className="flex flex-col gap-2.5">
              {data.recent_timeline.map((event, i) => (
                <motion.li
                  key={i}
                  initial={{ opacity: 0, x: -6 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.2, delay: i * 0.03 }}
                  className="flex items-center gap-2 text-sm"
                >
                  <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
                    Ch. {event.chapter}
                  </span>
                  {/* Curated beats carry a written summary; derived structural markers
                      fall back to their subject/predicate/object parts. */}
                  <span className="text-foreground">
                    {event.summary ??
                      [event.subject, event.predicate, event.object].filter(Boolean).join(' ')}
                  </span>
                </motion.li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
