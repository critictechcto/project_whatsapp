import type { AreaRoute } from '../registry/types'

/** Routes under /app/w/:workspaceId/. */
export const routes: AreaRoute[] = [
  {
    path: 'orders',
    handle: { title: 'Orders' },
    lazy: async () => ({ Component: (await import('./OrdersPage')).OrdersPage }),
  },
]
