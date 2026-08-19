export interface StateSnapshot {
  value: unknown
  chapter: number
  scene: number | null
  evidence_ids: string[]
  confidence: number
  reasoning: string
  timestamp: string
}

export interface StateEntryField {
  key: string
  current: StateSnapshot | null
  history: StateSnapshot[]
  importance: number
  dependencies: string[]
  element_type: string
  version: number
  last_mentioned_chapter: number
}

export interface Entity {
  id: string
  fields: Record<string, StateEntryField>
}

export const COLLECTIONS = [
  'characters',
  'relationships',
  'world',
  'themes',
  'motifs',
  'promises',
  'threats',
  'mysteries',
  'conflicts',
  'arcs',
  'style',
] as const

export type CollectionName = (typeof COLLECTIONS)[number]

export interface StateMetadata {
  last_processed_chapter: number
  total_chapters_processed: number
  created_at: string | null
  last_updated: string | null
}

export interface StateSummary {
  metadata: StateMetadata
  counts: Record<CollectionName, number> & {
    timeline_events: number
    raw_relations?: number
    evidence: number
  }
  open_promises: number
  unresolved_mysteries: number
  recent_timeline: TimelineEvent[]
}

/** An entry in the curated narrative chronology.
 *
 * `kind` separates the two things that live in this feed:
 *   'narrative'  - a story beat authored by the LLM timeline stage, carrying a
 *                  human-readable summary, a significance score and a reason it matters.
 *   'structural' - a marker the engine derived from character/inventory updates
 *                  (moves_to, dies, acquires, discards). Load-bearing for the
 *                  inspectors, but not something a reader wants in a chapter summary,
 *                  so the UI keeps these behind a toggle unless `reader_facing`.
 *
 * Raw dependency-parsed subject-verb-object triples are NOT timeline events; they
 * come back from the API separately as `raw_relations`.
 */
export interface TimelineEvent {
  chapter: number
  kind?: 'narrative' | 'structural'
  summary?: string
  subject?: string
  predicate?: string
  object?: string
  participants?: string[]
  location?: string | null
  time?: string | null
  event_type?: string | null
  significance?: number | null
  why_it_matters?: string | null
  causes?: string | null
  reader_facing?: boolean
  source?: string
  [key: string]: unknown
}

/** A dependency-parsed SVO triple: evidence the inspectors reason over, not a story
 * beat. Shown in the UI only behind an explicit "raw evidence" toggle. */
export interface RawRelation {
  chapter: number
  subject?: string
  predicate?: string
  object?: string
}

export interface TimelineResponse {
  events: TimelineEvent[]
  raw_relations: RawRelation[]
}

export interface Evidence {
  id: string
  text_span: string | null
  evidence_type: string
  source_chapter: number | null
  source_scene: number | null
  confidence: number
  related_entities: string[]
  interpretation_hint: string | null
  timestamp: string
}

export interface Finding {
  severity: string
  category: string
  title: string
  description: string
  chapter: number
  evidence_ids: string[]
  related_entities: string[]
  confidence: number
}

export interface ReportSummary {
  chapter: number
  generated_at: string | null
  inspector_count: number | null
  llm_provider: string | null
  finding_count: number
  severity_counts: Record<string, number>
}

export interface ReportDetail {
  metadata: {
    chapter: number
    generated_at: string
    inspector_count: number
    llm_provider: string
  }
  findings: Finding[]
  /** Short, human-readable story beats curated by the LLM critique call — distinct from
   * the mechanical subject-verb-object triples in the Timeline, which exist for structural
   * inspectors to reason over rather than for a human to read as a narrative summary. Absent
   * or empty on reports generated before this field existed, or when no LLM was available. */
  key_events?: string[]
}

export type GraphNodeType = 'character' | 'world' | 'theme' | 'event' | 'chapter'

export interface GraphNode {
  id: string
  label: string
  type: GraphNodeType | string
}

export type GraphEdgeType = 'relationship' | 'event_chapter' | string

export interface GraphEdge {
  id: string
  source: string
  target: string
  label: string
  type: GraphEdgeType
}

export interface GraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface IngestJob {
  id: string
  filename: string
  status: 'pending' | 'running' | 'done' | 'error'
  created_at: string
  finished_at: string | null
  result: {
    chapter_number: number
    delta_summary: string
    change_count: number
    finding_count: number
    graph_path: string
    total_chapters_processed: number
  } | null
  error: { message: string; traceback: string } | null
}
