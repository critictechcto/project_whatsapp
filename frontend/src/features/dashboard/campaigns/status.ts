import type { CampaignStatus } from './api'

export type CampaignAction = 'pause' | 'resume' | 'cancel'

/** Transitions the API allows from each status (`invalid_campaign_transition` otherwise). */
export const allowedActions: Record<CampaignStatus, readonly CampaignAction[]> = {
  draft: [],
  scheduled: ['cancel'],
  running: ['pause', 'cancel'],
  paused: ['resume', 'cancel'],
  completed: [],
  cancelled: [],
  failed: [],
}

/** PATCH works only in these statuses (`campaign_not_editable` otherwise). */
export function isEditable(status: CampaignStatus): boolean {
  return status === 'draft' || status === 'scheduled'
}

export const actionCopy: Record<
  CampaignAction,
  { label: string; title: string; description: string; confirm: string; success: string; danger?: boolean }
> = {
  pause: {
    label: 'Pause',
    title: 'Pause this campaign?',
    description: 'Messages that are not queued yet stay unsent until you resume. Messages already handed to Meta may still be delivered.',
    confirm: 'Pause campaign',
    success: 'Campaign paused',
  },
  resume: {
    label: 'Resume',
    title: 'Resume this campaign?',
    description: 'Sending continues with the remaining recipients. Consent is checked again before each message is sent.',
    confirm: 'Resume campaign',
    success: 'Campaign resumed',
  },
  cancel: {
    label: 'Cancel campaign',
    title: 'Cancel this campaign?',
    description: 'Recipients who have not been messaged yet will not receive it. This cannot be undone.',
    confirm: 'Cancel campaign',
    success: 'Campaign cancelled',
    danger: true,
  },
}
