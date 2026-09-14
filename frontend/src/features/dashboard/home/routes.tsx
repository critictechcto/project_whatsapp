import type { AreaRoute } from '../registry/types'

/** Workspace home at /app/w/:workspaceId/. */
export const routes: AreaRoute[] = [
  {
    index: true,
    handle: { title: 'Home' },
    lazy: async () => ({ Component: (await import('./HomePage')).HomePage }),
  },
]
