import { useMemo, useState } from 'react'
import { Search, Inbox } from 'lucide-react'
import type { CollectionName } from '@/types/state'
import { useCollection } from '@/lib/queries'
import { getPrimaryLabel, getLastMentionedChapter, COLLECTION_LABELS } from '@/lib/entityDisplay'
import { pluralize } from '@/lib/utils'
import { Input } from '@/components/ui/Input'
import { SkeletonGrid } from '@/components/ui/Skeleton'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { EntityCard } from '@/components/state/EntityCard'

interface CollectionPageProps {
  collection: CollectionName
  title?: string
  description?: string
  basePath?: string
}

export function CollectionPage({ collection, title, description, basePath }: CollectionPageProps) {
  const { data, isLoading, isError, error, refetch } = useCollection(collection)
  const [query, setQuery] = useState('')

  const entities = useMemo(() => {
    const all = data?.entities ?? []
    if (!query.trim()) return all
    const q = query.toLowerCase()
    return all.filter(
      (e) => getPrimaryLabel(collection, e).toLowerCase().includes(q) || e.id.toLowerCase().includes(q),
    )
  }, [data, query, collection])

  const sorted = useMemo(
    () => [...entities].sort((a, b) => getLastMentionedChapter(b) - getLastMentionedChapter(a)),
    [entities],
  )

  const path = basePath ?? `/${collection}`
  const label = COLLECTION_LABELS[collection]
  const labelPlural = pluralize(label)
  const labelPluralLower = labelPlural.toLowerCase()

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-1">
        <h2 className="text-xl font-semibold tracking-tight text-foreground">
          {title ?? labelPlural}
        </h2>
        <p className="text-sm text-muted-foreground">
          {description ?? `Everything the engine currently believes about tracked ${labelPluralLower}, with full version history.`}
        </p>
      </div>

      <div className="relative max-w-sm">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={`Search ${labelPluralLower}...`}
          className="pl-9"
        />
      </div>

      {isLoading && <SkeletonGrid />}

      {isError && (
        <ErrorState message={(error as Error)?.message ?? 'Failed to load data.'} onRetry={() => refetch()} />
      )}

      {!isLoading && !isError && sorted.length === 0 && (
        <EmptyState
          icon={<Inbox className="h-5 w-5" />}
          title={query ? `No ${labelPluralLower} match "${query}"` : `No ${labelPluralLower} tracked yet`}
          description={
            query
              ? 'Try a different search term.'
              : 'Ingest a chapter to start building the narrative state for this collection.'
          }
        />
      )}

      {!isLoading && !isError && sorted.length > 0 && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {sorted.map((entity, i) => (
            <EntityCard
              key={entity.id}
              entity={entity}
              collection={collection}
              to={`${path}/${encodeURIComponent(entity.id)}`}
              index={i}
            />
          ))}
        </div>
      )}
    </div>
  )
}
