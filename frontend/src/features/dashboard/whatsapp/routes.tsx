import { comingSoonRoute } from '../shell/comingSoon'
import type { AreaRoute } from '../registry/types'

/**
 * Routes under /app/w/:workspaceId/. Owned by the whatsapp feature agent.
 * Replace the placeholder with lazy routes, for example:
 *
 *   { path: 'whatsapp', handle: { title: 'WhatsApp' }, lazy: async () => ({ Component: (await import('./WhatsAppPage')).WhatsAppPage }) }
 */
export const routes: AreaRoute[] = [
  comingSoonRoute('whatsapp/*', 'WhatsApp', "Connect a number with Meta Embedded Signup and monitor quality rating and messaging limits."),
]
