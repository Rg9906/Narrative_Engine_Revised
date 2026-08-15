import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatChapter(chapter: number | null | undefined): string {
  if (chapter === null || chapter === undefined) return '—'
  return `Ch. ${chapter}`
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

export function formatRelativeChapter(chapter: number | null | undefined): string {
  if (chapter === null || chapter === undefined) return 'unknown'
  return `chapter ${chapter}`
}

/** Turns a snake_case / entity id into a readable label: "physical_hair_color" -> "Physical hair color". */
export function humanize(key: string): string {
  const spaced = key.replace(/_/g, ' ').trim()
  return spaced.charAt(0).toUpperCase() + spaced.slice(1)
}

export function titleCase(key: string): string {
  return key
    .split(/[_\s]+/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

/** Naive English pluralizer — sufficient for the fixed, known set of collection labels in this app. */
export function pluralize(word: string): string {
  if (/[^aeiou]y$/i.test(word)) return word.slice(0, -1) + 'ies'
  if (/(s|x|z|ch|sh)$/i.test(word)) return word + 'es'
  return word + 's'
}

export function clampPercent(value: number): number {
  return Math.max(0, Math.min(100, value))
}
