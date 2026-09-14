import type { AreaRoute } from '../registry/types'

/** Routes under /app/w/:workspaceId/. */
export const routes: AreaRoute[] = [
  {
    path: 'whatsapp',
    handle: { title: 'WhatsApp' },
    lazy: async () => ({ Component: (await import('./WhatsAppPage')).WhatsAppPage }),
  },
]
