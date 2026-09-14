import type { Tone } from '../../../components/app'
import type { Schemas } from '../../../api/types'

/**
 * Plain-language copy for values that come from Meta. Meta changes these rules from time to time,
 * so wording stays hedged ("set by Meta", "under Meta's current rules").
 */

const tierCustomers: Record<string, string | null> = {
  TIER_50: '50',
  TIER_250: '250',
  TIER_1K: '1,000',
  TIER_2K: '2,000',
  TIER_10K: '10,000',
  TIER_100K: '1,00,000',
  TIER_UNLIMITED: null,
}

/** "Up to 1,000 customers / 24h" for a Meta messaging limit tier. */
export function tierLabel(tier: string): string {
  if (!tier) return 'Not available yet'
  if (!(tier in tierCustomers)) return tier.replace(/^TIER_/, '').replace(/_/g, ' ')
  const customers = tierCustomers[tier]
  return customers ? `Up to ${customers} customers / 24h` : 'Unlimited'
}

export const tierExplanation =
  "Under Meta's current rules, the messaging limit caps how many different customers you can start conversations with in a rolling 24 hours. Meta raises it as you send more good-quality messages."

export const qualityExplanations: Record<Schemas['PhoneQualityRatingEnum'], string> = {
  GREEN: 'Customers are responding well to your messages.',
  YELLOW: 'Meta has seen some negative feedback, such as blocks or reports. Review who you message and how often.',
  RED: "Meta has seen a lot of negative feedback. Meta may limit sending if quality doesn't improve.",
  UNKNOWN: "Meta hasn't rated this number yet, usually because it has sent few messages.",
}

const nameStatuses: Record<string, { label: string; tone: Tone } | null> = {
  APPROVED: null,
  AVAILABLE_WITHOUT_REVIEW: null,
  NONE: null,
  PENDING_REVIEW: { label: 'Name in review', tone: 'amber' },
  DECLINED: { label: 'Name declined', tone: 'red' },
  EXPIRED: { label: 'Name expired', tone: 'red' },
}

/** Badge for Meta's display-name review, or null when there's nothing to flag. */
export function nameStatusBadge(nameStatus: string): { label: string; tone: Tone } | null {
  if (!nameStatus) return null
  if (nameStatus in nameStatuses) return nameStatuses[nameStatus]
  return { label: `Name: ${nameStatus.replace(/_/g, ' ').toLowerCase()}`, tone: 'neutral' }
}

export const onboardingBadges: Record<Schemas['WabaOnboardingStatusEnum'], { label: string; tone: Tone }> = {
  code_exchanged: { label: 'Connecting', tone: 'blue' },
  subscribing: { label: 'Connecting', tone: 'blue' },
  registering: { label: 'Registering number', tone: 'blue' },
  completed: { label: 'Connected', tone: 'green' },
  failed: { label: 'Setup failed', tone: 'red' },
}

export type SetupStepState = 'done' | 'current' | 'pending'

/** Progress steps after Meta's signup window closes, driven by `onboarding_status`. */
export function setupSteps(status: Schemas['WabaOnboardingStatusEnum'] | null): { label: string; state: SetupStepState }[] {
  const reached = status === null ? 1 : { code_exchanged: 1, subscribing: 1, registering: 2, completed: 4, failed: 1 }[status]
  const labels = [
    'Signed in with Meta and chose your business',
    'Connecting your WhatsApp Business Account',
    'Registering your phone number with the Cloud API',
    'Ready to send and receive messages',
  ]
  return labels.map((label, index) => ({
    label,
    state: index < reached ? 'done' : index === reached && status !== 'failed' ? 'current' : 'pending',
  }))
}
