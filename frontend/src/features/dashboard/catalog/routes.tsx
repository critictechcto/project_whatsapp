import type { AreaRoute } from '../registry/types'

/**
 * Routes under /app/w/:workspaceId/. Any member can read the catalog; writes are admin-only in the
 * API, so the screens hide or disable them for lower roles. Static `products/new` ranks above `:productId`.
 */
export const routes: AreaRoute[] = [
  {
    path: 'catalog',
    handle: { title: 'Catalog' },
    lazy: async () => ({ Component: (await import('./pages/ProductsPage')).ProductsPage }),
  },
  {
    path: 'catalog/collections',
    handle: { title: 'Collections' },
    lazy: async () => ({ Component: (await import('./pages/CollectionsPage')).CollectionsPage }),
  },
  {
    path: 'catalog/whatsapp',
    handle: { title: 'WhatsApp catalog' },
    lazy: async () => ({ Component: (await import('./pages/NativeCatalogPage')).NativeCatalogPage }),
  },
  {
    path: 'catalog/products/new',
    handle: { title: 'Add product', minRole: 'admin' },
    lazy: async () => ({ Component: (await import('./pages/ProductEditorPage')).ProductEditorPage }),
  },
  {
    path: 'catalog/products/:productId',
    handle: { title: 'Product' },
    lazy: async () => ({ Component: (await import('./pages/ProductEditorPage')).ProductEditorPage }),
  },
]
