import { comingSoonRoute } from '../shell/comingSoon'
import type { AreaRoute } from '../registry/types'

/**
 * Routes under /app/w/:workspaceId/. Owned by the templates feature agent.
 * Replace the placeholder with lazy routes, for example:
 *
 *   { path: 'templates', handle: { title: 'Templates' }, lazy: async () => ({ Component: (await import('./TemplatesPage')).TemplatesPage }) }
 */
export const routes: AreaRoute[] = [
  comingSoonRoute('templates/*', 'Templates', "Create message templates and track Meta's review status."),
]
