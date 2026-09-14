import type { AreaRoute } from '../registry/types'

/** Routes under /app/w/:workspaceId/. Store setup is for admins and owners. */
export const routes: AreaRoute[] = [
  {
    path: 'store',
    handle: { title: 'Store', minRole: 'admin' },
    lazy: async () => ({ Component: (await import('./StorePage')).StorePage }),
  },
]
