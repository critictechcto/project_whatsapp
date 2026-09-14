import type { CampaignRecipient } from './api'

export const skipReasonText: Record<string, string> = {
  opted_out: 'Skipped: this contact opted out of WhatsApp messages from you.',
  not_opted_in: 'Skipped: no marketing opt-in is recorded, and marketing templates need one.',
  invalid: 'Skipped: the phone number is not a valid WhatsApp number.',
}

/** Meta Cloud API error codes seen on campaign sends, in plain language. */
export const errorCodeText: Record<string, string> = {
  '131049':
    "Not delivered because of Meta's per-user marketing limit: Meta limits how many marketing messages one person receives from businesses. Meta suggests waiting before trying again.",
  '131050': 'The customer has turned off marketing messages from your business in WhatsApp.',
  '131026': "Undeliverable: the number may not be on WhatsApp, or the customer's app may need an update.",
  '131047': 'More than 24 hours have passed since the customer last messaged you, so only an approved template can be sent.',
  '131031': 'Meta has restricted the sending account.',
  '130472': "Not sent: the customer's number is part of a Meta experiment.",
  network_unknown: 'Delivery status is unknown after a network error. It was not retried automatically, to avoid sending twice.',
}

/** Skip reason or error in plain language; empty when there is nothing to explain. */
export function recipientDetail(recipient: Pick<CampaignRecipient, 'status' | 'skip_reason' | 'error_code'>): string {
  if (recipient.status === 'skipped') {
    if (!recipient.skip_reason) return 'Skipped.'
    return skipReasonText[recipient.skip_reason] ?? `Skipped: ${recipient.skip_reason.replace(/_/g, ' ')}.`
  }
  if (recipient.error_code) {
    return errorCodeText[recipient.error_code] ?? `Meta returned error ${recipient.error_code}.`
  }
  return ''
}
