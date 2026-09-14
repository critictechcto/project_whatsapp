import type { ComboboxOption } from '../../../components/app'
import { commonTimeZones } from '../../../lib/datetime'

/** Legacy IANA names some browsers still report, mapped to the names the backend stores. */
const ALIASES: Record<string, string> = {
  'Asia/Calcutta': 'Asia/Kolkata',
  'Asia/Katmandu': 'Asia/Kathmandu',
  'Asia/Saigon': 'Asia/Ho_Chi_Minh',
  'Asia/Rangoon': 'Asia/Yangon',
  'Asia/Dacca': 'Asia/Dhaka',
  'Etc/UTC': 'UTC',
}

export function canonicalTimeZone(zone: string): string {
  return ALIASES[zone] ?? zone
}

/** True when the runtime knows the IANA zone. */
export function isKnownTimeZone(zone: string): boolean {
  if (!zone) return false
  try {
    new Intl.DateTimeFormat('en-US', { timeZone: zone })
    return true
  } catch {
    return false
  }
}

function supportedZones(): string[] {
  try {
    const intl = Intl as typeof Intl & { supportedValuesOf?: (key: 'timeZone') => string[] }
    return intl.supportedValuesOf?.('timeZone') ?? []
  } catch {
    return []
  }
}

/** "GMT+05:30" (or "GMT" for UTC) at the given instant. */
export function utcOffsetLabel(zone: string, at: Date = new Date()): string {
  try {
    const part = new Intl.DateTimeFormat('en-US', { timeZone: zone, timeZoneName: 'longOffset' })
      .formatToParts(at)
      .find((p) => p.type === 'timeZoneName')
    return part?.value ?? ''
  } catch {
    return ''
  }
}

let cached: ComboboxOption[] | null = null

/** Every IANA zone the browser supports, common Indian-business zones first, labelled with their offset. */
export function timeZoneOptions(): ComboboxOption[] {
  if (cached) return cached
  const now = new Date()
  const common: string[] = [...commonTimeZones]
  const rest = supportedZones()
    .map(canonicalTimeZone)
    .filter((zone, index, all) => all.indexOf(zone) === index && !common.includes(zone))
    .sort((a, b) => a.localeCompare(b))

  cached = [...common, ...rest].map((zone) => {
    const offset = utcOffsetLabel(zone, now)
    return {
      value: zone,
      label: offset ? `${zone.replace(/_/g, ' ')} (${offset})` : zone.replace(/_/g, ' '),
      description: zone === 'Asia/Kolkata' ? 'India Standard Time' : undefined,
    }
  })
  return cached
}
