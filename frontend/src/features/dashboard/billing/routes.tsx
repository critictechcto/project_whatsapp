import { comingSoonRoute } from '../shell/comingSoon'
import type { AreaRoute } from '../registry/types'

/**
 * Routes under /app/w/:workspaceId/. Owned by the billing feature agent.
 * Replace the placeholder with lazy routes, for example:
 *
 *   { path: 'billing', handle: { title: 'Billing' }, lazy: async () => ({ Component: (await import('./BillingPage')).BillingPage }) }
 */
export const routes: AreaRoute[] = [
  comingSoonRoute('billing/*', 'Billing', "Plans, invoices with GST and usage."),
]
