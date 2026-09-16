/**
 * Plain-language copy for Meta's Cloud API error codes on failed outbound messages
 * (`Message.error_code`). Codes and meanings follow Meta's error reference at the time of writing;
 * anything unknown falls back to Meta's own message.
 */

type DeliveryErrorCopy = {
  /** One short sentence, shown after "Not delivered:". */
  reason: string
  /** Optional next step for the business. */
  action?: string
}

const copyByCode: Record<string, DeliveryErrorCopy> = {
  // Business eligibility payment issue.
  '131042': {
    reason: 'add a payment method in WhatsApp Manager',
    action:
      "Meta reported a problem with the payment method of this WhatsApp Business Account. Add or update it in WhatsApp Manager, then send the update again.",
  },
  '131047': {
    reason: 'the 24-hour customer service window had closed',
    action: 'Outside the window WhatsApp only allows approved template messages.',
  },
  '470': {
    reason: 'the 24-hour customer service window had closed',
    action: 'Outside the window WhatsApp only allows approved template messages.',
  },
  '131026': {
    reason: "WhatsApp couldn't deliver it to this number",
    action: 'The number may not be on WhatsApp, or the customer may need to update the app.',
  },
  '131049': {
    reason: 'Meta held this message back for this customer',
    action: 'Meta may limit how many marketing messages a person receives. Try again later.',
  },
  '131050': { reason: 'the customer has stopped marketing messages from this business' },
  '131048': {
    reason: 'Meta limited sending from this number',
    action: 'Meta may restrict sending when too many earlier messages were blocked or reported as spam.',
  },
  '131056': {
    reason: 'too many messages were sent to this customer in a short time',
    action: 'Wait a little, then try again.',
  },
  '131031': {
    reason: 'Meta has restricted or locked this WhatsApp Business Account',
    action: 'Check the account status in WhatsApp Manager.',
  },
  '1026': { reason: "the customer's WhatsApp app can't show this kind of message" },
}

export type DeliveryError = {
  /** "Not delivered: …" for the bubble. */
  summary: string
  action?: string
  /** True when the code was recognised (Meta's raw message isn't needed). */
  known: boolean
}

export function describeDeliveryError(code: string | null | undefined, message?: string | null): DeliveryError {
  const copy = code ? copyByCode[code] : undefined
  if (copy) return { summary: `Not delivered: ${copy.reason}.`, action: copy.action, known: true }
  const detail = message?.trim()
  return { summary: detail ? `Not delivered: ${detail}` : 'Not delivered.', known: false }
}
