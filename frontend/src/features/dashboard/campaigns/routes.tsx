import { comingSoonRoute } from '../shell/comingSoon'
import type { AreaRoute } from '../registry/types'

/**
 * Routes under /app/w/:workspaceId/. Owned by the campaigns feature agent.
 * Replace the placeholder with lazy routes, for example:
 *
 *   { path: 'campaigns', handle: { title: 'Campaigns' }, lazy: async () => ({ Component: (await import('./CampaignsPage')).CampaignsPage }) }
 */
export const routes: AreaRoute[] = [
  comingSoonRoute('campaigns/*', 'Campaigns', "Send approved templates to tagged audiences now or on a schedule."),
]
