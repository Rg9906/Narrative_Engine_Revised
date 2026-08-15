import type { CollectionName, Entity, StateEntryField } from '@/types/state'
import { humanize, titleCase } from '@/lib/utils'

const LABEL_FIELD_PRIORITY = [
  'canonical_name',
  'relationship_label',
  'theme_name',
  'symbol_name',
  'promise_text',
  'foreshadow_text',
  'mystery_text',
  'threat_text',
  'clue_text',
  'description',
  'type',
]

function currentValue(field: StateEntryField | undefined): unknown {
  return field?.current?.value ?? null
}

/** Best-effort human label for an entity — tries known "name-like" fields, falls back to the id. */
export function getPrimaryLabel(collection: string, entity: Entity): string {
  for (const key of LABEL_FIELD_PRIORITY) {
    const value = currentValue(entity.fields[key])
    if (typeof value === 'string' && value.trim()) return value
  }

  if (collection === 'relationships' && entity.id.includes('::')) {
    const [a, b] = entity.id.split('::')
    return `${titleCase(a)} ↔ ${titleCase(b)}`
  }

  return titleCase(entity.id)
}

/** Small set of fields worth showing as a preview on a card, in priority order. */
const SUMMARY_FIELD_PRIORITY = [
  'status',
  'type',
  'arc_stage',
  'emotional_state',
  'mention_count',
  'last_interaction_chapter',
  'last_mentioned_chapter',
]

export function getSummaryChips(entity: Entity): { key: string; value: string }[] {
  const chips: { key: string; value: string }[] = []
  for (const key of SUMMARY_FIELD_PRIORITY) {
    const field = entity.fields[key]
    const value = currentValue(field)
    if (value === null || value === undefined || value === '') continue
    chips.push({ key, value: Array.isArray(value) ? value.join(', ') : String(value) })
    if (chips.length >= 3) break
  }
  return chips
}

export function averageImportance(entity: Entity): number {
  const fields = Object.values(entity.fields)
  if (fields.length === 0) return 0
  return fields.reduce((sum, f) => sum + f.importance, 0) / fields.length
}

export function getLastMentionedChapter(entity: Entity): number {
  const fields = Object.values(entity.fields)
  if (fields.length === 0) return 0
  return Math.max(...fields.map((f) => f.last_mentioned_chapter ?? 0))
}

const STATUS_TONE: Record<string, 'success' | 'warning' | 'destructive' | 'default'> = {
  OPEN: 'warning',
  UNRESOLVED: 'warning',
  FULFILLED: 'success',
  RESOLVED: 'success',
  CLOSED: 'success',
  ABANDONED: 'destructive',
  BROKEN: 'destructive',
}

export function statusTone(status: string | undefined | null): 'success' | 'warning' | 'destructive' | 'default' {
  if (!status) return 'default'
  return STATUS_TONE[status.toUpperCase()] ?? 'default'
}

export function fieldLabel(key: string): string {
  return humanize(key)
}

export const COLLECTION_LABELS: Record<CollectionName, string> = {
  characters: 'Character',
  relationships: 'Relationship',
  world: 'World Element',
  themes: 'Theme',
  motifs: 'Motif',
  promises: 'Promise',
  threats: 'Threat',
  mysteries: 'Mystery',
  conflicts: 'Conflict',
  arcs: 'Arc',
  style: 'Style Note',
}
