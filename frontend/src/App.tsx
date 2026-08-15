import { Route, Routes } from 'react-router-dom'
import { AppShell } from '@/components/layout/AppShell'
import { OverviewPage } from '@/pages/OverviewPage'
import { CollectionPage } from '@/pages/CollectionPage'
import { EntityDetailPage } from '@/pages/EntityDetailPage'
import { GroupedCollectionPage } from '@/pages/GroupedCollectionPage'
import { TimelinePage } from '@/pages/TimelinePage'
import { GraphPage } from '@/pages/GraphPage'
import { ReportsPage } from '@/pages/ReportsPage'
import { ReportDetailPage } from '@/pages/ReportDetailPage'
import { IngestPage } from '@/pages/IngestPage'
import { NotFoundPage } from '@/pages/NotFoundPage'

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<OverviewPage />} />

        <Route path="characters" element={<CollectionPage collection="characters" />} />
        <Route path="characters/:id" element={<EntityDetailPage collection="characters" />} />

        <Route path="relationships" element={<CollectionPage collection="relationships" />} />
        <Route path="relationships/:id" element={<EntityDetailPage collection="relationships" />} />

        <Route path="world" element={<CollectionPage collection="world" />} />
        <Route path="world/:id" element={<EntityDetailPage collection="world" />} />

        <Route
          path="themes"
          element={
            <GroupedCollectionPage
              title="Themes & Motifs"
              description="Recurring ideas and symbolic objects the engine has detected across chapters."
              basePathPrefix="/themes"
              tabs={[
                { value: 'themes', label: 'Themes' },
                { value: 'motifs', label: 'Motifs' },
              ]}
            />
          }
        />
        <Route path="themes/:collection/:id" element={<EntityDetailPage />} />

        <Route
          path="promises"
          element={
            <GroupedCollectionPage
              title="Promises & Mysteries"
              description="Foreshadowing, open questions, and threats the story has set up but not yet paid off."
              basePathPrefix="/promises"
              tabs={[
                { value: 'promises', label: 'Promises' },
                { value: 'mysteries', label: 'Mysteries' },
                { value: 'threats', label: 'Threats' },
              ]}
            />
          }
        />
        <Route path="promises/:collection/:id" element={<EntityDetailPage />} />

        <Route
          path="dynamics"
          element={
            <GroupedCollectionPage
              title="Conflicts & Arcs"
              description="Dramatic conflicts and character arc stages the engine is tracking across chapters."
              basePathPrefix="/dynamics"
              tabs={[
                { value: 'conflicts', label: 'Conflicts' },
                { value: 'arcs', label: 'Arcs' },
              ]}
            />
          }
        />
        <Route path="dynamics/:collection/:id" element={<EntityDetailPage />} />

        <Route path="style" element={<CollectionPage collection="style" title="Style & Readability" description="Prose-level metrics tracked across the whole manuscript: sentence structure, dialogue density, sentiment, and readability." />} />
        <Route path="style/:id" element={<EntityDetailPage collection="style" backTo="/style" />} />

        <Route path="timeline" element={<TimelinePage />} />
        <Route path="graph" element={<GraphPage />} />
        <Route path="reports" element={<ReportsPage />} />
        <Route path="reports/:chapter" element={<ReportDetailPage />} />
        <Route path="ingest" element={<IngestPage />} />

        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  )
}
