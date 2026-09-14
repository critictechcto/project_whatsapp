import type { AreaRoute } from '../registry/types'

/** Routes under /app/w/:workspaceId/. Static paths rank above `automations/:id`. */
export const routes: AreaRoute[] = [
  {
    path: 'automations',
    handle: { title: 'Automations' },
    lazy: async () => ({ Component: (await import('./RulesPage')).RulesPage }),
  },
  {
    path: 'automations/new',
    handle: { title: 'New rule', minRole: 'admin' },
    lazy: async () => ({ Component: (await import('./RuleEditorPage')).RuleEditorPage }),
  },
  {
    path: 'automations/business-hours',
    handle: { title: 'Business hours' },
    lazy: async () => ({ Component: (await import('./BusinessHoursPage')).BusinessHoursPage }),
  },
  {
    path: 'automations/runs',
    handle: { title: 'Run log' },
    lazy: async () => ({ Component: (await import('./RunLogPage')).RunLogPage }),
  },
  {
    path: 'automations/:id',
    handle: { title: 'Automation rule' },
    lazy: async () => ({ Component: (await import('./RuleEditorPage')).RuleEditorPage }),
  },
]
