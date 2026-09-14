import { TZDate } from '@date-fns/tz'
import { format, formatDistanceToNowStrict } from 'date-fns'

export const DEFAULT_TIME_ZONE = 'Asia/Kolkata'

/** Formats an ISO timestamp in a time zone with a date-fns pattern. */
export function formatInZone(iso: string, timeZone: string = DEFAULT_TIME_ZONE, pattern = 'd MMM yyyy, h:mm a'): string {
  return format(new TZDate(new Date(iso).getTime(), timeZone), pattern)
}

/** "10 Sep 2026, 3:00 PM" in the workspace zone. */
export function formatDateTime(iso: string | null | undefined, timeZone: string = DEFAULT_TIME_ZONE): string {
  return iso ? formatInZone(iso, timeZone) : '—'
}

/** "10 Sep 2026" in the workspace zone. */
export function formatDate(iso: string | null | undefined, timeZone: string = DEFAULT_TIME_ZONE): string {
  return iso ? formatInZone(iso, timeZone, 'd MMM yyyy') : '—'
}

/** "5 minutes ago" / "in 3 hours". */
export function formatRelative(iso: string | null | undefined): string {
  return iso ? formatDistanceToNowStrict(new Date(iso), { addSuffix: true }) : '—'
}

/** Short zone name for labels, e.g. "IST" or "GMT+5:30". */
export function timeZoneName(timeZone: string = DEFAULT_TIME_ZONE, at = new Date()): string {
  try {
    const part = new Intl.DateTimeFormat('en-IN', { timeZone, timeZoneName: 'short' })
      .formatToParts(at)
      .find((p) => p.type === 'timeZoneName')
    return part?.value ?? timeZone
  } catch {
    return timeZone
  }
}

/** ISO instant → `{ date: 'yyyy-MM-dd', time: 'HH:mm' }` wall-clock parts in the zone. */
export function toZonedParts(iso: string, timeZone: string = DEFAULT_TIME_ZONE): { date: string; time: string } {
  const zoned = new TZDate(new Date(iso).getTime(), timeZone)
  return { date: format(zoned, 'yyyy-MM-dd'), time: format(zoned, 'HH:mm') }
}

/** Wall-clock `yyyy-MM-dd` + `HH:mm` in the zone → UTC ISO string (`...Z`). Null if incomplete. */
export function fromZonedParts(date: string, time: string, timeZone: string = DEFAULT_TIME_ZONE): string | null {
  const d = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date)
  const t = /^(\d{2}):(\d{2})$/.exec(time)
  if (!d || !t) return null
  const zoned = new TZDate(Number(d[1]), Number(d[2]) - 1, Number(d[3]), Number(t[1]), Number(t[2]), 0, timeZone)
  return new Date(zoned.getTime()).toISOString()
}

/** Common IANA zones for the workspace time-zone select (India first). */
export const commonTimeZones = [
  'Asia/Kolkata',
  'Asia/Dubai',
  'Asia/Singapore',
  'Asia/Kathmandu',
  'Asia/Dhaka',
  'Europe/London',
  'America/New_York',
  'UTC',
] as const
