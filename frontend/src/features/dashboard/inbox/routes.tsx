import { comingSoonRoute } from '../shell/comingSoon'
import type { AreaRoute } from '../registry/types'

/**
 * Routes under /app/w/:workspaceId/. Owned by the inbox feature agent.
 * Replace the placeholder with lazy routes, for example:
 *
 *   { path: 'inbox', handle: { title: 'Inbox' }, lazy: async () => ({ Component: (await import('./InboxPage')).InboxPage }) }
 */
export const routes: AreaRoute[] = [
  comingSoonRoute('inbox/*', 'Inbox', "Reply to customers from one shared inbox, inside the 24-hour customer service window."),
]
