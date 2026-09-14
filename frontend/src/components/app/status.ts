export type Tone = 'neutral' | 'green' | 'amber' | 'red' | 'blue'

type StatusInfo = { label: string; tone: Tone }

/**
 * Labels and tones for API statuses (templates, phone numbers, messages, campaigns, subscriptions…).
 * Keys are the raw enum values; lookups are case-sensitive because Meta uses UPPER_CASE.
 */
export const statusMap: Record<string, StatusInfo> = {
  // Templates (Meta)
  DRAFT: { label: 'Draft', tone: 'neutral' },
  PENDING: { label: 'In review', tone: 'amber' },
  APPROVED: { label: 'Approved', tone: 'green' },
  REJECTED: { label: 'Rejected', tone: 'red' },
  PAUSED: { label: 'Paused', tone: 'amber' },
  DISABLED: { label: 'Disabled', tone: 'red' },
  IN_APPEAL: { label: 'In appeal', tone: 'amber' },
  PENDING_DELETION: { label: 'Pending deletion', tone: 'neutral' },
  DELETED: { label: 'Deleted', tone: 'neutral' },
  LIMIT_EXCEEDED: { label: 'Limit exceeded', tone: 'red' },
  ARCHIVED: { label: 'Archived', tone: 'neutral' },
  // Quality rating
  GREEN: { label: 'High quality', tone: 'green' },
  YELLOW: { label: 'Medium quality', tone: 'amber' },
  RED: { label: 'Low quality', tone: 'red' },
  UNKNOWN: { label: 'Not rated', tone: 'neutral' },
  // Messages / recipients
  queued: { label: 'Queued', tone: 'neutral' },
  sending: { label: 'Sending', tone: 'blue' },
  sent: { label: 'Sent', tone: 'blue' },
  delivered: { label: 'Delivered', tone: 'green' },
  read: { label: 'Read', tone: 'green' },
  failed: { label: 'Failed', tone: 'red' },
  received: { label: 'Received', tone: 'neutral' },
  skipped: { label: 'Skipped', tone: 'neutral' },
  // Campaigns
  draft: { label: 'Draft', tone: 'neutral' },
  scheduled: { label: 'Scheduled', tone: 'blue' },
  running: { label: 'Running', tone: 'blue' },
  paused: { label: 'Paused', tone: 'amber' },
  completed: { label: 'Completed', tone: 'green' },
  cancelled: { label: 'Cancelled', tone: 'neutral' },
  // Conversations
  open: { label: 'Open', tone: 'green' },
  closed: { label: 'Closed', tone: 'neutral' },
  // Subscriptions / invoices / invitations
  trialing: { label: 'Trial', tone: 'blue' },
  active: { label: 'Active', tone: 'green' },
  halted: { label: 'Payment failed', tone: 'red' },
  expired: { label: 'Expired', tone: 'neutral' },
  issued: { label: 'Issued', tone: 'amber' },
  paid: { label: 'Paid', tone: 'green' },
  void: { label: 'Void', tone: 'neutral' },
  pending: { label: 'Pending', tone: 'amber' },
  accepted: { label: 'Accepted', tone: 'green' },
  revoked: { label: 'Revoked', tone: 'neutral' },
  // Phone registration / WABA
  registered: { label: 'Registered', tone: 'green' },
  deregistered: { label: 'Deregistered', tone: 'neutral' },
  restricted: { label: 'Restricted', tone: 'red' },
  disabled: { label: 'Disabled', tone: 'red' },
  disconnected: { label: 'Disconnected', tone: 'neutral' },
  // Consent
  opted_in: { label: 'Opted in', tone: 'green' },
  opted_out: { label: 'Opted out', tone: 'red' },
  unknown: { label: 'No opt-in', tone: 'neutral' },
}

export function statusInfo(status: string): StatusInfo {
  return statusMap[status] ?? { label: status.replace(/_/g, ' ').toLowerCase().replace(/^\w/, (c) => c.toUpperCase()), tone: 'neutral' }
}
