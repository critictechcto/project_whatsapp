import { errorMessage, isApiError } from '../../../api/errors'

export type FriendlyError = {
  message: string
  /** Show a link to billing (plan limits). */
  billing?: boolean
}

/** Clear messages for the campaign error codes in the wave-2 contract. */
export function campaignError(error: unknown): FriendlyError {
  if (isApiError(error, 'template_not_approved')) {
    return {
      message:
        "Meta hasn't approved this template (or its approval was paused), so it can't be sent. Choose an approved template or wait for Meta's review.",
    }
  }
  if (isApiError(error, 'campaign_not_editable')) {
    return {
      message: 'This campaign has already started, so it can no longer be changed. Open its report to pause or cancel it.',
    }
  }
  if (isApiError(error, 'invalid_campaign_transition')) {
    return {
      message: "That action isn't available for the campaign's current status. It may have changed in the meantime, so the latest status is shown.",
    }
  }
  if (isApiError(error, 'quota_exceeded')) {
    return {
      message: `${error.message || "Your plan's limit has been reached."} Upgrade your plan to continue.`,
      billing: true,
    }
  }
  if (isApiError(error, 'insufficient_role')) {
    return { message: "Your role doesn't allow this. Ask a workspace owner or admin." }
  }
  return { message: errorMessage(error) }
}
