import { comingSoonRoute } from '../shell/comingSoon'
import type { AreaRoute } from '../registry/types'

/**
 * Routes under /app/w/:workspaceId/. Owned by the team feature agent.
 * Replace the placeholder with lazy routes, for example:
 *
 *   { path: 'team', handle: { title: 'Team' }, lazy: async () => ({ Component: (await import('./TeamPage')).TeamPage }) }
 */
export const routes: AreaRoute[] = [
  comingSoonRoute('team/*', 'Team', "Invite teammates and manage their roles."),
]
