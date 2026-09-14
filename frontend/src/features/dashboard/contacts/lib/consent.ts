import type { Tone } from '../../../../components/app'
import type { ConsentAction, ConsentSource, OptInStatus } from './types'

export const optInStatuses: readonly OptInStatus[] = ['opted_in', 'opted_out', 'unknown']

export const optInInfo: Record<OptInStatus, { label: string; tone: Tone; explanation: string }> = {
  opted_in: {
    label: 'Opted in',
    tone: 'green',
    explanation: 'A marketing opt-in is on record, so this contact can receive marketing templates.',
  },
  opted_out: {
    label: 'Opted out',
    tone: 'red',
    explanation: 'This contact opted out of marketing messages. Campaigns skip them until they opt in again.',
  },
  unknown: {
    label: 'Unknown',
    tone: 'neutral',
    explanation: 'No marketing opt-in is on record. Record one before sending marketing templates.',
  },
}

export const consentActionLabels: Record<ConsentAction, string> = {
  opt_in: 'Opted in',
  opt_out: 'Opted out',
}

/** Where a consent change came from, phrased for the timeline. */
export function consentSourceLabel(source: ConsentSource, action: ConsentAction): string {
  switch (source) {
    case 'manual':
      return 'Recorded manually'
    case 'import':
      return 'CSV import'
    case 'api':
      return 'API'
    case 'whatsapp_keyword':
      return action === 'opt_out' ? 'Sent STOP on WhatsApp' : 'Sent START on WhatsApp'
    case 'meta_marketing_optout':
      return 'Stopped marketing messages in WhatsApp (reported by Meta)'
    default:
      return source
  }
}

/** Short label for `Contact.opt_in_source` (a consent source value, or free text from older data). */
export function optInSourceLabel(source: string): string {
  const known: Record<string, string> = {
    manual: 'Recorded manually',
    import: 'CSV import',
    api: 'API',
    whatsapp_keyword: 'WhatsApp keyword',
    meta_marketing_optout: 'Meta',
  }
  return known[source] ?? source
}
