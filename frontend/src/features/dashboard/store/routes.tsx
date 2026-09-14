import type { AreaRoute } from '../registry/types'

/** Routes under /app/w/:workspaceId/. Store setup is for admins and owners. */
export const routes: AreaRoute[] = [
  {
    path: 'store',
    handle: { title: 'Store setup', minRole: 'admin' },
    lazy: async () => ({ Component: (await import('./SetupPage')).SetupPage }),
  },
  {
    path: 'store/settings',
    handle: { title: 'Store settings', minRole: 'admin' },
    lazy: async () => ({ Component: (await import('./StoreSettingsPage')).StoreSettingsPage }),
  },
  {
    path: 'store/payments',
    handle: { title: 'Payments', minRole: 'admin' },
    lazy: async () => ({ Component: (await import('./PaymentsPage')).PaymentsPage }),
  },
  {
    path: 'store/alerts',
    handle: { title: 'Order alerts', minRole: 'admin' },
    lazy: async () => ({ Component: (await import('./AlertsPage')).AlertsPage }),
  },
  {
    path: 'store/notifications',
    handle: { title: 'Buyer notifications', minRole: 'admin' },
    lazy: async () => ({ Component: (await import('./NotificationsPage')).NotificationsPage }),
  },
]
