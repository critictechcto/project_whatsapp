import type { AreaRoute } from '../registry/types'

/** Routes under /app/w/:workspaceId/. */
export const routes: AreaRoute[] = [
  {
    path: 'team',
    handle: { title: 'Team' },
    lazy: async () => ({ Component: (await import('./TeamPage')).TeamPage }),
  },
]
