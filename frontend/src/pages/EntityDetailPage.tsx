import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, FileQuestion } from 'lucide-react'
import type { CollectionName } from '@/types/state'
import { useEntity } from '@/lib/queries'
import { getPrimaryLabel, COLLECTION_LABELS, averageImportance } from '@/lib/entityDisplay'
import { pluralize } from '@/lib/utils'
import { Skeleton } from '@/components/ui/Skeleton'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { Badge } from '@/components/ui/Badge'
import { FieldCard } from '@/components/state/FieldCard'

interface EntityDetailPageProps {
  collection?: CollectionName
  backTo?: string
}

// Collections grouped under a tabbed parent route (see App.tsx) don't have their own
// top-level path — the back link has to land on the parent route with the right tab selected.
const GROUP_BACK_PATH: Partial<Record<CollectionName, string>> = {
  themes: '/themes?tab=themes',
  motifs: '/themes?tab=motifs',
  promises: '/promises?tab=promises',
  mysteries: '/promises?tab=mysteries',
  threats: '/promises?tab=threats',
  conflicts: '/dynamics?tab=conflicts',
  arcs: '/dynamics?tab=arcs',
}

export function EntityDetailPage({ collection: collectionProp, backTo }: EntityDetailPageProps) {
  const params = useParams<{ collection?: string; id: string }>()
  const collection = (collectionProp ?? params.collection) as CollectionName
  const id = params.id as string

  const { data: entity, isLoading, isError, error, refetch } = useEntity(collection, id)
  const back = backTo ?? GROUP_BACK_PATH[collection] ?? `/${collection}`

  return (
    <div className="flex flex-col gap-5">
      <Link
        to={back}
        className="inline-flex w-fit items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to {pluralize(COLLECTION_LABELS[collection] ?? collection).toLowerCase()}
      </Link>

      {isLoading && (
        <div className="flex flex-col gap-4">
          <Skeleton className="h-8 w-64" />
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-28 w-full" />
            ))}
          </div>
        </div>
      )}

      {isError && (
        <ErrorState
          message={(error as Error)?.message ?? 'Failed to load this entity.'}
          onRetry={() => refetch()}
        />
      )}

      {!isLoading && !isError && !entity && (
        <EmptyState icon={<FileQuestion className="h-5 w-5" />} title="Not found" description="This entity no longer exists in the narrative state." />
      )}

      {entity && (
        <>
          <div className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="accent">{COLLECTION_LABELS[collection]}</Badge>
              <span className="font-mono text-xs text-muted-foreground">{entity.id}</span>
            </div>
            <h2 className="text-2xl font-semibold tracking-tight text-foreground">
              {getPrimaryLabel(collection, entity)}
            </h2>
            <p className="text-sm text-muted-foreground">
              {Object.keys(entity.fields).length} tracked fields · avg. importance{' '}
              {Math.round(averageImportance(entity) * 100)}%
            </p>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {Object.values(entity.fields)
              .sort((a, b) => b.importance - a.importance)
              .map((field) => (
                <FieldCard key={field.key} field={field} />
              ))}
          </div>
        </>
      )}
    </div>
  )
}
