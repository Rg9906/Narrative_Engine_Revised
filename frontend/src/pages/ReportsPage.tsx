import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { FileWarning, ChevronRight, Sparkles } from 'lucide-react'
import { useReports } from '@/lib/queries'
import { SkeletonGrid } from '@/components/ui/Skeleton'
import { ErrorState } from '@/components/ui/ErrorState'
import { EmptyState } from '@/components/ui/EmptyState'
import { Badge } from '@/components/ui/Badge'
import { formatChapter, formatDate } from '@/lib/utils'

const SEVERITY_VARIANT: Record<string, 'destructive' | 'warning' | 'accent' | 'default'> = {
  error: 'destructive',
  warning: 'warning',
  suggestion: 'accent',
  note: 'default',
}

export function ReportsPage() {
  const { data, isLoading, isError, error, refetch } = useReports()
  const reports = data?.reports ?? []

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-1">
        <h2 className="text-xl font-semibold tracking-tight text-foreground">Editorial Reports</h2>
        <p className="text-sm text-muted-foreground">
          Developmental critique per chapter — static inspector findings plus grounded LLM commentary.
        </p>
      </div>

      {isLoading && <SkeletonGrid count={3} />}

      {isError && <ErrorState message={(error as Error)?.message ?? 'Failed to load reports.'} onRetry={() => refetch()} />}

      {!isLoading && !isError && reports.length === 0 && (
        <EmptyState
          icon={<FileWarning className="h-5 w-5" />}
          title="No editorial reports yet"
          description="Ingest a chapter to generate the first editorial critique."
        />
      )}

      {!isLoading && !isError && reports.length > 0 && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {reports.map((report, i) => (
            <motion.div
              key={report.chapter}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.25, delay: Math.min(i * 0.04, 0.3) }}
            >
              <Link
                to={`/reports/${report.chapter}`}
                className="group flex flex-col gap-3 rounded-xl border border-border bg-surface p-5 shadow-soft transition-all duration-150 hover:-translate-y-0.5 hover:border-border-strong hover:shadow-elevated"
              >
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-sm font-semibold text-foreground">{formatChapter(report.chapter)}</p>
                    <p className="text-xs text-muted-foreground">{formatDate(report.generated_at)}</p>
                  </div>
                  <ChevronRight className="h-4 w-4 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
                </div>

                <div className="flex flex-wrap gap-1.5">
                  {Object.entries(report.severity_counts).map(([severity, count]) => (
                    <Badge key={severity} variant={SEVERITY_VARIANT[severity] ?? 'default'}>
                      {count} {severity}
                    </Badge>
                  ))}
                </div>

                <div className="mt-auto flex items-center justify-between text-xs text-muted-foreground">
                  {/* finding_count is the RANKED count once a synthesis pass has run.
                      The raw total is shown alongside it so the triage is visible rather
                      than looking like findings went missing. */}
                  <span>
                    {report.finding_count} finding{report.finding_count === 1 ? '' : 's'}
                    {report.raw_finding_count !== undefined &&
                      report.raw_finding_count > report.finding_count &&
                      ` of ${report.raw_finding_count} raw`}
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <Sparkles className="h-3 w-3" />
                    {report.llm_provider ?? 'none'}
                  </span>
                </div>
              </Link>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  )
}
