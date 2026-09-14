import type { AreaRoute } from '../registry/types'

/** Routes under /app/w/:workspaceId/. */
export const routes: AreaRoute[] = [
  {
    path: 'campaigns',
    handle: { title: 'Campaigns' },
    lazy: async () => ({ Component: (await import('./CampaignsPage')).CampaignsPage }),
  },
  {
    path: 'campaigns/new',
    handle: { title: 'New campaign', minRole: 'admin' },
    lazy: async () => ({ Component: (await import('./CampaignWizardPage')).CampaignWizardPage }),
  },
  {
    path: 'campaigns/:id',
    handle: { title: 'Campaign report' },
    lazy: async () => ({ Component: (await import('./CampaignDetailPage')).CampaignDetailPage }),
  },
  {
    path: 'campaigns/:id/edit',
    handle: { title: 'Edit campaign', minRole: 'admin' },
    lazy: async () => ({ Component: (await import('./CampaignWizardPage')).CampaignWizardPage }),
  },
]
