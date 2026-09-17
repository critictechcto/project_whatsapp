import type { AreaRoute } from '../registry/types'

/** Analytics at /app/w/:workspaceId/analytics. Range and tab live in the URL: `?from=2026-08-19&to=2026-09-17&tab=campaigns`. */
export const routes: AreaRoute[] = [
  {
    path: 'analytics',
    handle: { title: 'Analytics' },
    lazy: async () => ({ Component: (await import('./AnalyticsPage')).AnalyticsPage }),
  },
]
