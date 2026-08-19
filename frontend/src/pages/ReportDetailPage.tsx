import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ArrowLeft, CheckCircle2, FileWarning, PenLine, Sparkles } from 'lucide-react'
import { useReport } from '@/lib/queries'
import type { Finding } from '@/types/state'
import { Skeleton } from '@/components/ui/Skeleton'
import { ErrorState } from '@/components/ui/ErrorState'
import { EmptyState } from '@/components/ui/EmptyState'
import { Badge } from '@/components/ui/Badge'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/Card'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/Tabs'
import { FindingCard } from '@/components/reports/FindingCard'
import { TopFindingCard } from '@/components/reports/TopFindingCard'
import { SignalGroupCard } from '@/components/reports/SignalGroupCard'
import { formatChapter, formatDate } from '@/lib/utils'

export function ReportDetailPage() {
  const { chapter } = useParams<{ chapter: string }>()
  const chapterNum = Number(chapter)
  const { data: report, isLoading, isError, error, refetch } = useReport(chapterNum)
  const [tab, setTab] = useState('all')

  const topFindings = report?.top_findings ?? []
  const signals = report?.signals ?? []
  const strengths = report?.strengths ?? []
  const letter = (report?.editorial_letter ?? '').trim()

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
      <Link
        to="/reports"
        className="inline-flex w-fit items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
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
        <ErrorState
          message={(error as Error)?.message ?? `No report for chapter ${chapter}.`}
          onRetry={() => refetch()}
        />
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
              {report.metadata.raw_finding_count !== undefined && (
                <>
                  {' · '}
                  {report.metadata.raw_finding_count} raw findings triaged into {signals.length} distinct
                  signal{signals.length === 1 ? '' : 's'}
                </>
              )}
            </p>
          </div>

          {/* The letter is the report's actual verdict, so it leads. */}
          {letter && (
            <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }}>
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-1.5">
                    <PenLine className="h-4 w-4 text-primary" />
                    Editorial assessment
                  </CardTitle>
                  <CardDescription>
                    Written after ranking every rule-based signal and first-pass reading against the chapter text.
                  </CardDescription>
                </CardHeader>
                <CardContent className="flex flex-col gap-3">
                  {letter.split(/\n\s*\n/).map((paragraph, i) => (
                    <p key={i} className="text-sm leading-relaxed text-foreground">
                      {paragraph}
                    </p>
                  ))}
                </CardContent>
              </Card>
            </motion.div>
          )}

          {strengths.length > 0 && (
            <Card className="border-success/30 bg-success/5">
              <CardHeader>
                <CardTitle className="flex items-center gap-1.5">
                  <CheckCircle2 className="h-4 w-4 text-success" />
                  What's working
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="flex flex-col gap-2">
                  {strengths.map((strength, i) => (
                    <li key={i} className="flex gap-2 text-sm text-foreground">
                      <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-success" />
                      {strength}
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}

          {topFindings.length > 0 && (
            <div className="flex flex-col gap-3">
              <div className="flex flex-col gap-1">
                <h3 className="text-lg font-semibold tracking-tight text-foreground">
                  What to fix first
                </h3>
                <p className="text-sm text-muted-foreground">
                  Ranked by what an editor would raise with the author first. Duplicate and
                  low-value detector output has been merged or dropped — the full raw feed is
                  further down.
                </p>
              </div>
              {topFindings.map((finding, i) => (
                <TopFindingCard key={i} finding={finding} />
              ))}
            </div>
          )}

          {report.key_events && report.key_events.length > 0 && (
            <Card className="border-accent/30 bg-accent/5">
              <CardHeader>
                <CardTitle className="flex items-center gap-1.5">
                  <Sparkles className="h-4 w-4 text-accent" />
                  Key events
                </CardTitle>
                <CardDescription>
                  What actually happened in this chapter, in plain English.
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
          )}

          {signals.length > 0 && (
            <div className="flex flex-col gap-3">
              <div className="flex flex-col gap-1">
                <h3 className="text-lg font-semibold tracking-tight text-foreground">
                  Rule-based signals
                </h3>
                <p className="text-sm text-muted-foreground">
                  Raw output from the {report.metadata.inspector_count} mechanical inspectors,
                  deduplicated. Shown so the assessment above can be audited — a signal appearing
                  here was a lead, not necessarily a conclusion.
                </p>
              </div>
              <div className="flex flex-col gap-2">
                {signals.map((signal, i) => (
                  <SignalGroupCard key={i} signal={signal} />
                ))}
              </div>
            </div>
          )}

          {report.findings.length === 0 ? (
            <EmptyState
              icon={<FileWarning className="h-5 w-5" />}
              title="No findings"
              description="This chapter passed every inspector cleanly."
            />
          ) : (
            <details className="rounded-lg border border-border bg-surface">
              <summary className="cursor-pointer px-4 py-3 text-sm font-medium text-foreground">
                All {report.findings.length} raw findings, ungrouped
              </summary>
              <div className="border-t border-border p-4">
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
              </div>
            </details>
          )}
        </>
      )}
    </div>
  )
}
