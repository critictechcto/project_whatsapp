import type { TemplateCategory, TemplateStatus } from '../../../../api/types'

export const categoryOptions: { value: TemplateCategory; label: string; summary: string; pricing: string }[] = [
  {
    value: 'MARKETING',
    label: 'Marketing',
    summary: 'Offers, festive sales, product announcements and re-engagement messages.',
    pricing:
      "Under Meta's current pricing, marketing is usually the highest-priced category, and Meta may limit how many marketing messages a customer receives. Send only to contacts who opted in.",
  },
  {
    value: 'UTILITY',
    label: 'Utility',
    summary: 'Updates about something the customer already did: orders, deliveries, bookings, payments.',
    pricing:
      "Under Meta's current pricing, utility messages cost less than marketing and may be free inside an open 24-hour customer service window. Promotional content can get the template recategorised or rejected.",
  },
  {
    value: 'AUTHENTICATION',
    label: 'Authentication',
    summary: 'One-time passcodes for login or verification. Meta supplies the message text.',
    pricing: "Charged per message under Meta's current pricing. Use it only for verification codes.",
  },
]

export const categoryLabels: Record<TemplateCategory, string> = {
  MARKETING: 'Marketing',
  UTILITY: 'Utility',
  AUTHENTICATION: 'Authentication',
}

/** Languages Indian businesses use most. Meta supports more; codes follow Meta's format. */
export const languageOptions: { value: string; label: string }[] = [
  { value: 'en', label: 'English' },
  { value: 'en_US', label: 'English (US)' },
  { value: 'en_GB', label: 'English (UK)' },
  { value: 'hi', label: 'Hindi' },
  { value: 'bn', label: 'Bengali' },
  { value: 'gu', label: 'Gujarati' },
  { value: 'kn', label: 'Kannada' },
  { value: 'ml', label: 'Malayalam' },
  { value: 'mr', label: 'Marathi' },
  { value: 'pa', label: 'Punjabi' },
  { value: 'ta', label: 'Tamil' },
  { value: 'te', label: 'Telugu' },
  { value: 'ur', label: 'Urdu' },
]

export function languageLabel(code: string): string {
  return languageOptions.find((option) => option.value === code)?.label ?? code
}

/** Statuses offered in the list filter, in the order users think about them. */
export const statusFilterOptions: { value: TemplateStatus; label: string }[] = [
  { value: 'APPROVED', label: 'Approved' },
  { value: 'PENDING', label: 'In review' },
  { value: 'REJECTED', label: 'Rejected' },
  { value: 'PAUSED', label: 'Paused' },
  { value: 'DISABLED', label: 'Disabled' },
  { value: 'DRAFT', label: 'Draft' },
]

/** Meta's `rejected_reason` values with plain-language guidance. Unknown reasons fall back to a generic note. */
const rejectionReasons: Record<string, { label: string; explanation: string }> = {
  INVALID_FORMAT: {
    label: 'Invalid format',
    explanation:
      'Meta found a formatting problem, often variables without sample values, variables next to each other, or unusual characters. Check the variables and examples, then submit again.',
  },
  INCORRECT_CATEGORY: {
    label: 'Incorrect category',
    explanation:
      "The content didn't match the chosen category. Messages with offers or promotions usually need the Marketing category.",
  },
  PROMOTIONAL: {
    label: 'Promotional content',
    explanation: 'Meta treated the content as promotional for this category. Remove the offer or choose Marketing.',
  },
  TAG_CONTENT_MISMATCH: {
    label: 'Content does not match the category',
    explanation: "The template's language or category doesn't match its content. Check both before submitting again.",
  },
  ABUSIVE_CONTENT: {
    label: 'Content not allowed',
    explanation: "Meta found content that may break WhatsApp's Business and Commerce policies. Rewrite the message.",
  },
  SCAM: {
    label: 'Possible scam',
    explanation: 'Meta flagged the message as potentially misleading. Make the sender, purpose and any links clear.',
  },
  CATEGORY_NOT_AVAILABLE: {
    label: 'Category not available',
    explanation: "This category isn't available for your WhatsApp Business Account right now.",
  },
}

export function rejectionInfo(reason: string): { label: string; explanation: string } {
  const known = rejectionReasons[reason.toUpperCase()]
  if (known) return known
  return {
    label: reason ? reason.replace(/_/g, ' ').toLowerCase().replace(/^\w/, (c) => c.toUpperCase()) : 'No reason given',
    explanation: "Meta didn't give more detail. Review WhatsApp's template guidelines, adjust the template and submit again.",
  }
}

export const qualityExplanations: Record<string, string> = {
  GREEN: 'Customers are responding well to this template.',
  YELLOW: 'Meta has seen some negative feedback, such as blocks or reports. Review the content and audience.',
  RED: 'Meta has seen a lot of negative feedback. Meta may pause or disable the template if this continues.',
  UNKNOWN: 'Meta rates quality once the template has been sent to enough customers.',
}

export const statusExplanations: Partial<Record<TemplateStatus, string>> = {
  DRAFT: 'Saved in UpChatz only. Submit it to send it to Meta for review.',
  PENDING: 'Meta is reviewing this template. Reviews often finish within minutes but can take up to 24 hours or longer.',
  APPROVED: 'Approved by Meta. You can send it to customers, including outside the 24-hour customer service window.',
  REJECTED: 'Meta rejected this template. Edit it and submit again.',
  PAUSED: 'Meta paused this template after negative customer feedback. It cannot be sent while paused.',
  DISABLED: 'Meta disabled this template after repeated quality issues. It cannot be sent.',
  IN_APPEAL: 'An appeal of the rejection is in progress with Meta.',
  PENDING_DELETION: 'This template is being deleted at Meta.',
  DELETED: 'This template no longer exists at Meta.',
  LIMIT_EXCEEDED: "The WhatsApp Business Account reached Meta's template limit.",
  ARCHIVED: 'Archived at Meta.',
}

/** Templates in these statuses can be edited and submitted (same rule as the API). */
export const EDITABLE_STATUSES: readonly TemplateStatus[] = ['DRAFT', 'REJECTED']
