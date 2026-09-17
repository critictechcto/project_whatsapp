import { TZDate } from '@date-fns/tz'
import { format } from 'date-fns'
import type { DateRange } from './types'

/** Longest range the API accepts, in days (inclusive). */
export const MAX_RANGE_DAYS = 92
export const DEFAULT_PRESET_DAYS = 30

export type RangePreset = '7' | '30' | '90' | 'custom'

export const presetOptions: { value: RangePreset; label: string }[] = [
  { value: '7', label: 'Last 7 days' },
  { value: '30', label: 'Last 30 days' },
  { value: '90', label: 'Last 90 days' },
  { value: 'custom', label: 'Custom range' },
]

const DAY_MS = 86_400_000
const DATE = /^(\d{4})-(\d{2})-(\d{2})$/

/** `YYYY-MM-DD` → UTC midnight in ms, or null for anything that isn't a real calendar date. */
function dateValue(date: string): number | null {
  const match = DATE.exec(date)
  if (!match) return null
  const ms = Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]))
  return new Date(ms).toISOString().slice(0, 10) === date ? ms : null
}

export function isValidDate(date: string): boolean {
  return dateValue(date) !== null
}

/** Adds whole days to a `YYYY-MM-DD` date. */
export function addDays(date: string, days: number): string {
  const ms = dateValue(date)
  if (ms === null) return date
  return new Date(ms + days * DAY_MS).toISOString().slice(0, 10)
}

/** Days from `from` to `to`, both included (`2026-09-01`..`2026-09-01` is 1). */
export function daysInRange(from: string, to: string): number {
  const a = dateValue(from)
  const b = dateValue(to)
  if (a === null || b === null) return 0
  return Math.round((b - a) / DAY_MS) + 1
}

/** Every date from `from` to `to`, oldest first. */
export function eachDate(from: string, to: string): string[] {
  const count = daysInRange(from, to)
  return Array.from({ length: Math.max(0, count) }, (_, i) => addDays(from, i))
}

/** Today's date in the workspace time zone. */
export function todayIn(timeZone: string, now = Date.now()): string {
  return format(new TZDate(now, timeZone), 'yyyy-MM-dd')
}

/** The last `days` days ending today. */
export function presetRange(days: number, today: string): DateRange {
  return { from: addDays(today, -(days - 1)), to: today }
}

/** The same-length period immediately before the range. */
export function previousRange({ from, to }: DateRange): DateRange {
  const length = daysInRange(from, to)
  return { from: addDays(from, -length), to: addDays(from, -1) }
}

/** The API's rules for `from`/`to`; returns a message, or null when the range is fine. */
export function validateRange(range: Partial<DateRange>, today: string): string | null {
  if (!range.from || !range.to) return 'Choose a start and an end date.'
  if (!isValidDate(range.from) || !isValidDate(range.to)) return 'Enter valid dates.'
  if (range.from > range.to) return 'The start date must be on or before the end date.'
  if (range.to > today) return "The end date can't be in the future."
  if (daysInRange(range.from, range.to) > MAX_RANGE_DAYS) return `Choose a range of at most ${MAX_RANGE_DAYS} days.`
  return null
}

/**
 * Range from the URL query (`?from=&to=`). Missing or invalid params fall back to the last 30 days
 * (the API default), so a bad shared link still shows a report.
 */
export function rangeFromSearch(search: URLSearchParams, today: string): { range: DateRange; invalid: boolean } {
  const from = search.get('from')
  const to = search.get('to')
  if (!from && !to) return { range: presetRange(DEFAULT_PRESET_DAYS, today), invalid: false }
  const candidate = { from: from ?? '', to: to ?? '' }
  if (validateRange(candidate, today)) return { range: presetRange(DEFAULT_PRESET_DAYS, today), invalid: true }
  return { range: candidate, invalid: false }
}

/** Which preset a range matches, or `custom`. */
export function presetOf(range: DateRange, today: string): RangePreset {
  if (range.to !== today) return 'custom'
  const days = daysInRange(range.from, range.to)
  return days === 7 ? '7' : days === 30 ? '30' : days === 90 ? '90' : 'custom'
}

/** "1 Sep – 30 Sep 2026" (year shown once when both dates share it). */
export function formatRangeLabel({ from, to }: DateRange): string {
  const a = dateValue(from)
  const b = dateValue(to)
  if (a === null || b === null) return `${from} – ${to}`
  const opts = { day: 'numeric', month: 'short', timeZone: 'UTC' } as const
  const sameYear = from.slice(0, 4) === to.slice(0, 4)
  const start = new Intl.DateTimeFormat('en-IN', sameYear ? opts : { ...opts, year: 'numeric' }).format(a)
  const end = new Intl.DateTimeFormat('en-IN', { ...opts, year: 'numeric' }).format(b)
  return from === to ? end : `${start} – ${end}`
}

/** Short axis label for a series date: "7 Sep". */
export function formatDayLabel(date: string): string {
  const ms = dateValue(date)
  if (ms === null) return date
  return new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', timeZone: 'UTC' }).format(ms)
}
