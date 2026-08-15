import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Share2 } from 'lucide-react'
import { useGraph } from '@/lib/queries'
import { GraphCanvas, NODE_TYPE_LABELS, NODE_TYPE_ORDER } from '@/components/graph/GraphCanvas'
import { Skeleton } from '@/components/ui/Skeleton'
import { ErrorState } from '@/components/ui/ErrorState'
import { EmptyState } from '@/components/ui/EmptyState'
import { Input } from '@/components/ui/Input'
import { cn } from '@/lib/utils'
import type { GraphNode, GraphNodeType } from '@/types/state'

const NODE_TYPE_DOT_CLASS: Record<GraphNodeType, string> = {
  character: 'bg-primary',
  world: 'bg-success',
  theme: 'bg-accent',
  event: 'bg-warning',
  chapter: 'bg-muted-foreground',
}

const NAVIGABLE_COLLECTION: Partial<Record<GraphNodeType, string>> = {
  character: 'characters',
  world: 'world',
  theme: 'themes',
}

function entityIdFromNodeId(nodeId: string): string {
  const idx = nodeId.indexOf('::')
  return idx === -1 ? nodeId : nodeId.slice(idx + 2)
}

export function GraphPage() {
  const { data, isLoading, isError, error, refetch } = useGraph()
  const [hiddenTypes, setHiddenTypes] = useState<Set<string>>(new Set(['event', 'chapter']))
  const [query, setQuery] = useState('')
  const navigate = useNavigate()

  function toggleType(type: string) {
    setHiddenTypes((prev) => {
      const next = new Set(prev)
      if (next.has(type)) next.delete(type)
      else next.add(type)
      return next
    })
  }

  function handleNodeClick(node: GraphNode) {
    const collection = NAVIGABLE_COLLECTION[node.type as GraphNodeType]
    if (!collection) return
    const entityId = entityIdFromNodeId(node.id)
    if (collection === 'themes') {
      navigate(`/themes/themes/${encodeURIComponent(entityId)}`)
    } else {
      navigate(`/${collection}/${encodeURIComponent(entityId)}`)
    }
  }

  const typeCounts = new Map<string, number>()
  for (const n of data?.nodes ?? []) {
    typeCounts.set(n.type, (typeCounts.get(n.type) ?? 0) + 1)
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-1">
        <h2 className="text-xl font-semibold tracking-tight text-foreground">Story Graph</h2>
        <p className="text-sm text-muted-foreground">
          Characters, world elements, themes, events, and chapters as one living network. Drag to reposition, scroll
          to zoom, click a node to open it.
        </p>
      </div>

      {isLoading && (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-9 w-64" />
          <Skeleton className="h-[520px] w-full" />
        </div>
      )}

      {isError && (
        <ErrorState message={(error as Error)?.message ?? 'Failed to load the story graph.'} onRetry={() => refetch()} />
      )}

      {!isLoading && !isError && (!data || data.nodes.length === 0) && (
        <EmptyState
          icon={<Share2 className="h-5 w-5" />}
          title="No graph yet"
          description="The story graph builds automatically once a chapter has been ingested."
        />
      )}

      {!isLoading && !isError && data && data.nodes.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, ease: 'easeOut' }}
          className="flex flex-col gap-3"
        >
          <div className="flex flex-wrap items-center gap-3">
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search nodes..."
              className="max-w-xs"
            />
            <div className="flex flex-wrap items-center gap-1.5">
              {NODE_TYPE_ORDER.filter((type) => typeCounts.has(type)).map((type) => {
                const active = !hiddenTypes.has(type)
                return (
                  <button
                    key={type}
                    onClick={() => toggleType(type)}
                    className={cn(
                      'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors',
                      active
                        ? 'border-border-strong bg-surface text-foreground'
                        : 'border-border bg-transparent text-muted-foreground/50',
                    )}
                  >
                    <span className={cn('h-2 w-2 rounded-full', active ? NODE_TYPE_DOT_CLASS[type] : 'bg-muted-foreground/30')} />
                    {NODE_TYPE_LABELS[type]}
                    <span className="text-muted-foreground/70">{typeCounts.get(type)}</span>
                  </button>
                )
              })}
            </div>
            <span className="ml-auto text-xs text-muted-foreground">
              {data.nodes.length} nodes · {data.edges.length} connections
            </span>
          </div>

          <GraphCanvas
            data={data}
            hiddenTypes={hiddenTypes}
            searchQuery={query}
            onNodeClick={handleNodeClick}
            className="h-[70vh] min-h-[420px] rounded-xl border border-border bg-surface shadow-soft"
          />
        </motion.div>
      )}
    </div>
  )
}
