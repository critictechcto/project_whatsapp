import type { AreaRoute } from '../registry/types'

/** Routes under /app/w/:workspaceId/. Billing is for admins and owners; only owners can pay or edit. */
export const routes: AreaRoute[] = [
  {
    path: 'billing',
    handle: { title: 'Billing', minRole: 'admin' },
    lazy: async () => ({ Component: (await import('./BillingPage')).BillingPage }),
  },
  {
    path: 'billing/plans',
    handle: { title: 'Plans', minRole: 'admin' },
    lazy: async () => ({ Component: (await import('./PlansPage')).PlansPage }),
  },
  {
    path: 'billing/profile',
    handle: { title: 'Billing details', minRole: 'admin' },
    lazy: async () => ({ Component: (await import('./BillingProfilePage')).BillingProfilePage }),
  },
]
