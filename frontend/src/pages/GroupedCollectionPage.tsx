import { useSearchParams } from 'react-router-dom'
import type { CollectionName } from '@/types/state'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/Tabs'
import { CollectionPage } from '@/pages/CollectionPage'

interface GroupedCollectionPageProps {
  title: string
  description: string
  basePathPrefix: string
  tabs: { value: CollectionName; label: string }[]
}

export function GroupedCollectionPage({ title, description, basePathPrefix, tabs }: GroupedCollectionPageProps) {
  const [params, setParams] = useSearchParams()
  const active = (params.get('tab') as CollectionName) || tabs[0].value

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-1">
        <h2 className="text-xl font-semibold tracking-tight text-foreground">{title}</h2>
        <p className="text-sm text-muted-foreground">{description}</p>
      </div>

      <Tabs value={active} onValueChange={(v) => setParams({ tab: v }, { replace: true })}>
        <TabsList>
          {tabs.map((t) => (
            <TabsTrigger key={t.value} value={t.value}>
              {t.label}
            </TabsTrigger>
          ))}
        </TabsList>
        {tabs.map((t) => (
          <TabsContent key={t.value} value={t.value}>
            <CollectionPage
              collection={t.value}
              title={t.label}
              basePath={`${basePathPrefix}/${t.value}`}
            />
          </TabsContent>
        ))}
      </Tabs>
    </div>
  )
}
