import { comingSoonRoute } from '../shell/comingSoon'
import type { AreaRoute } from '../registry/types'

/**
 * Routes under /app/w/:workspaceId/. Owned by the contacts feature agent.
 * Replace the placeholder with lazy routes, for example:
 *
 *   { path: 'contacts', handle: { title: 'Contacts' }, lazy: async () => ({ Component: (await import('./ContactsPage')).ContactsPage }) }
 */
export const routes: AreaRoute[] = [
  comingSoonRoute('contacts/*', 'Contacts', "Import contacts, tag them and keep a record of opt-ins and opt-outs."),
]
