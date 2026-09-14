import { comingSoonRoute } from '../shell/comingSoon'
import type { AreaRoute } from '../registry/types'

/**
 * Routes under /app/w/:workspaceId/. Owned by the automations feature agent.
 * Replace the placeholder with lazy routes, for example:
 *
 *   { path: 'automations', handle: { title: 'Automations' }, lazy: async () => ({ Component: (await import('./AutomationsPage')).AutomationsPage }) }
 */
export const routes: AreaRoute[] = [
  comingSoonRoute('automations/*', 'Automations', "Keyword replies, welcome messages and away messages outside business hours."),
]
