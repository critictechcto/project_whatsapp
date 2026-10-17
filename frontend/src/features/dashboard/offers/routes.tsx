import type { AreaRoute } from '../registry/types'

/** Routes under /app/w/:workspaceId/. `offers/new` ranks above `offers/:id`. */
export const routes: AreaRoute[] = [
  {
    path: 'offers',
    handle: { title: 'Offers' },
    lazy: async () => ({ Component: (await import('./OffersPage')).OffersPage }),
  },
  {
    path: 'offers/new',
    handle: { title: 'New offer code', minRole: 'admin' },
    lazy: async () => ({ Component: (await import('./OfferEditorPage')).OfferEditorPage }),
  },
  {
    path: 'offers/:id',
    handle: { title: 'Offer code' },
    lazy: async () => ({ Component: (await import('./OfferDetailPage')).OfferDetailPage }),
  },
  {
    path: 'offers/:id/edit',
    handle: { title: 'Edit offer code', minRole: 'admin' },
    lazy: async () => ({ Component: (await import('./OfferEditorPage')).OfferEditorPage }),
  },
]
