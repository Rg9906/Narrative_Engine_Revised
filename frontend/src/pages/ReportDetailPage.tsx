import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ArrowLeft, FileWarning, Sparkles } from 'lucide-react'
import { useReport } from '@/lib/queries'
import type { Finding } from '@/types/state'
import { Skeleton } from '@/components/ui/Skeleton'
import { ErrorState } from '@/components/ui/ErrorState'
import { EmptyState } from '@/components/ui/EmptyState'
import { Badge } from '@/components/ui/Badge'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/Card'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/Tabs'
import { FindingCard } from '@/components/reports/FindingCard'
import { formatChapter, formatDate } from '@/lib/utils'

export function ReportDetailPage() {
  const { chapter } = useParams<{ chapter: string }>()
  const chapterNum = Number(chapter)
  const { data: report, isLoading, isError, error, refetch } = useReport(chapterNum)
  const [tab, setTab] = useState('all')

  const bySeverity = useMemo(() => {
    const groups = new Map<string, Finding[]>()
    for (const f of report?.findings ?? []) {
      const key = f.severity.toLowerCase()
      if (!groups.has(key)) groups.set(key, [])
      groups.get(key)!.push(f)
    }
    return groups
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [report])

  const severities = [...bySeverity.keys()].sort()
  const visibleFindings = tab === 'all' ? report?.findings ?? [] : bySeverity.get(tab) ?? []

  return (
    <div className="flex flex-col gap-5">
      <Link to="/reports" className="inline-flex w-fit items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground">
        <ArrowLeft className="h-4 w-4" />
        Back to reports
      </Link>

      {isLoading && (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-8 w-56" />
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-20 w-full" />
          ))}
        </div>
      )}

      {isError && (
        <ErrorState message={(error as Error)?.message ?? `No report for chapter ${chapter}.`} onRetry={() => refetch()} />
      )}

      {!isLoading && !isError && report && (
        <>
          <div className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="accent">{formatChapter(report.metadata.chapter)}</Badge>
              <span className="text-xs text-muted-foreground">{formatDate(report.metadata.generated_at)}</span>
            </div>
            <h2 className="text-2xl font-semibold tracking-tight text-foreground">Editorial Report</h2>
            <p className="text-sm text-muted-foreground">
              {report.metadata.inspector_count} static inspectors · LLM provider: {report.metadata.llm_provider}
            </p>
          </div>

          {report.key_events && report.key_events.length > 0 && (
            <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }}>
              <Card className="border-accent/30 bg-accent/5">
                <CardHeader>
                  <CardTitle className="flex items-center gap-1.5">
                    <Sparkles className="h-4 w-4 text-accent" />
                    Key events
                  </CardTitle>
                  <CardDescription>
                    What actually happened in this chapter, curated by the LLM critique — not the raw extracted
                    event log below.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <ul className="flex flex-col gap-2">
                    {report.key_events.map((event, i) => (
                      <li key={i} className="flex gap-2 text-sm text-foreground">
                        <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
                        {event}
                      </li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
            </motion.div>
          )}

          {report.findings.length === 0 ? (
            <EmptyState icon={<FileWarning className="h-5 w-5" />} title="No findings" description="This chapter passed every inspector cleanly." />
          ) : (
            <Tabs value={tab} onValueChange={setTab}>
              <TabsList>
                <TabsTrigger value="all">All ({report.findings.length})</TabsTrigger>
                {severities.map((s) => (
                  <TabsTrigger key={s} value={s}>
                    {s} ({bySeverity.get(s)!.length})
                  </TabsTrigger>
                ))}
              </TabsList>
              <TabsContent value={tab} className="flex flex-col gap-2.5">
                {visibleFindings.map((f, i) => (
                  <FindingCard key={i} finding={f} />
                ))}
              </TabsContent>
            </Tabs>
          )}
        </>
      )}
    </div>
  )
}
