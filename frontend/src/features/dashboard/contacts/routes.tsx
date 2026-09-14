import type { AreaRoute } from '../registry/types'

/**
 * Routes under /app/w/:workspaceId/. Static segments (`tags`, `imports`) rank above `:contactId`.
 * Role gates follow the API: contacts and tags are readable by any member, imports need agent
 * to read and admin to upload.
 */
export const routes: AreaRoute[] = [
  {
    path: 'contacts',
    handle: { title: 'Contacts' },
    lazy: async () => ({ Component: (await import('./pages/ContactsListPage')).ContactsListPage }),
  },
  {
    path: 'contacts/tags',
    handle: { title: 'Tags' },
    lazy: async () => ({ Component: (await import('./pages/TagsPage')).TagsPage }),
  },
  {
    path: 'contacts/imports',
    handle: { title: 'Contact imports', minRole: 'agent' },
    lazy: async () => ({ Component: (await import('./pages/ImportsPage')).ImportsPage }),
  },
  {
    path: 'contacts/imports/new',
    handle: { title: 'Import contacts', minRole: 'admin' },
    lazy: async () => ({ Component: (await import('./pages/ImportWizardPage')).ImportWizardPage }),
  },
  {
    path: 'contacts/imports/:importId',
    handle: { title: 'Contact import', minRole: 'agent' },
    lazy: async () => ({ Component: (await import('./pages/ImportStatusPage')).ImportStatusPage }),
  },
  {
    path: 'contacts/:contactId',
    handle: { title: 'Contact' },
    lazy: async () => ({ Component: (await import('./pages/ContactDetailPage')).ContactDetailPage }),
  },
]
