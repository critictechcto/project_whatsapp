import type { AreaRoute } from '../registry/types'

/** Routes under /app/w/:workspaceId/. Creating and editing templates needs admin, like the API. */
export const routes: AreaRoute[] = [
  {
    path: 'templates',
    handle: { title: 'Templates' },
    lazy: async () => ({ Component: (await import('./TemplatesListPage')).TemplatesListPage }),
  },
  {
    path: 'templates/new',
    handle: { title: 'New template', minRole: 'admin' },
    lazy: async () => ({ Component: (await import('./TemplateBuilderPage')).TemplateBuilderPage }),
  },
  {
    path: 'templates/:id',
    handle: { title: 'Template' },
    lazy: async () => ({ Component: (await import('./TemplateDetailPage')).TemplateDetailPage }),
  },
  {
    path: 'templates/:id/edit',
    handle: { title: 'Edit template', minRole: 'admin' },
    lazy: async () => ({ Component: (await import('./TemplateBuilderPage')).TemplateBuilderPage }),
  },
]
