import type { AreaRoute } from '../registry/types'

/** Routes under /app/w/:workspaceId/. */
export const routes: AreaRoute[] = [
  {
    path: 'catalog',
    handle: { title: 'Catalog' },
    lazy: async () => ({ Component: (await import('./CatalogPage')).CatalogPage }),
  },
]
