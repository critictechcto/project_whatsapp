import type { AreaRoute } from '../registry/types'

/**
 * Routes under /app/w/:workspaceId/. The list keeps its filters in the URL:
 * `?tab=open&payment=cod_pending&method=cod&from=2026-09-01&to=2026-09-14&q=ananya`.
 */
export const routes: AreaRoute[] = [
  {
    path: 'orders',
    handle: { title: 'Orders' },
    lazy: async () => ({ Component: (await import('./OrdersPage')).OrdersPage }),
  },
  {
    path: 'orders/:orderId',
    handle: { title: 'Order' },
    lazy: async () => ({ Component: (await import('./OrderDetailPage')).OrderDetailPage }),
  },
]
