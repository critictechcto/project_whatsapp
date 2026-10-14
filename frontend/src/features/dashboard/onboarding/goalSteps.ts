import type { WorkspaceGoal } from './api'

/**
 * Getting-started steps and their order for the workspace goals (docs/contracts/onboarding.md).
 * A workspace may pick several goals; Home renders the steps with live state and the welcome flow
 * previews the order.
 */
export type Goals = readonly WorkspaceGoal[]

/** Goals in their fixed order, without repeats (the order the API stores them in). */
export function normalizeGoals(goals: Goals): WorkspaceGoal[] {
  return goalOptions.map((option) => option.value).filter((goal) => goals.includes(goal))
}

export type ChecklistStepId = 'whatsapp' | 'products' | 'payments' | 'store' | 'contacts' | 'templates' | 'campaigns' | 'automations' | 'team'

/** Steps whose state comes from the store checklist (`GET /api/v1/store/checklist/`). */
export const COMMERCE_STEPS: readonly ChecklistStepId[] = ['products', 'payments', 'store']

export type StepDefinition = {
  id: ChecklistStepId
  title: string
  description: string
  /** Relative to `/app/w/:workspaceId/`. */
  to: string
  cta: string
}

export const stepDefinitions: Record<ChecklistStepId, StepDefinition> = {
  whatsapp: {
    id: 'whatsapp',
    title: 'Connect WhatsApp',
    description: "Link your business number to the official WhatsApp Business Platform with Meta's Embedded Signup.",
    to: 'whatsapp',
    cta: 'Connect number',
  },
  products: {
    id: 'products',
    title: 'Add products',
    description: 'Add what you sell with prices and photos, so buyers can browse them in the chat.',
    to: 'catalog',
    cta: 'Add products',
  },
  payments: {
    id: 'payments',
    title: 'Set up payments',
    description: 'Connect your own Razorpay or Cashfree account, or offer cash on delivery.',
    to: 'store/payments',
    cta: 'Set up payments',
  },
  store: {
    id: 'store',
    title: 'Turn on your store',
    description: 'Buyers can then browse, order and pay inside WhatsApp.',
    to: 'store',
    cta: 'Open store',
  },
  contacts: {
    id: 'contacts',
    title: 'Add contacts',
    description: 'Import customers who agreed to hear from you on WhatsApp, with their opt-in recorded.',
    to: 'contacts',
    cta: 'Add contacts',
  },
  templates: {
    id: 'templates',
    title: 'Create a template',
    description: 'Messages you start outside the 24-hour customer service window need a template approved by Meta.',
    to: 'templates',
    cta: 'Create template',
  },
  campaigns: {
    id: 'campaigns',
    title: 'Send your first campaign',
    description: 'Send an approved template to a tagged group of opted-in contacts, now or on a schedule.',
    to: 'campaigns/new',
    cta: 'New campaign',
  },
  automations: {
    id: 'automations',
    title: 'Set up an automation',
    description: 'Reply automatically to keywords, first messages or messages outside business hours.',
    to: 'automations',
    cta: 'Add automation',
  },
  team: {
    id: 'team',
    title: 'Invite your team',
    description: 'Share the inbox with colleagues and choose what each person can do.',
    to: 'team',
    cta: 'Invite teammates',
  },
}

/** The order without a goal. */
export const DEFAULT_ORDER: readonly ChecklistStepId[] = ['whatsapp', 'contacts', 'templates', 'campaigns', 'automations', 'team']

/** Each goal's own first steps; with several goals these come first, in goal order. */
const goalFirstSteps: Record<WorkspaceGoal, readonly ChecklistStepId[]> = {
  sell: ['whatsapp', 'products', 'payments', 'store'],
  marketing: ['whatsapp', 'contacts', 'templates', 'campaigns'],
  support: ['whatsapp', 'team', 'automations', 'contacts'],
}

/** Each goal's full list; the rest of every chosen goal's list follows the first steps. */
const goalOrders: Record<WorkspaceGoal, readonly ChecklistStepId[]> = {
  sell: ['whatsapp', 'products', 'payments', 'store', 'contacts', 'templates', 'team'],
  marketing: ['whatsapp', 'contacts', 'templates', 'campaigns', 'automations', 'team'],
  support: ['whatsapp', 'team', 'automations', 'contacts', 'templates', 'campaigns'],
}

/** One line per step on why it matters for a goal; steps without one use `defaultWhy`. */
const goalWhy: Record<WorkspaceGoal, Partial<Record<ChecklistStepId, string>>> = {
  sell: {
    whatsapp: 'Buyers message this number to see your products and order.',
    products: 'Your menu in the chat: buyers pick from these.',
    payments: 'Buyers pay you directly; the money never passes through us.',
    store: 'Your shop opens to every buyer who messages you.',
    contacts: 'Past buyers who opted in can hear about new stock.',
    templates: 'Order updates outside the 24-hour window need approved templates.',
  },
  marketing: {
    whatsapp: 'Offers go out from your own verified business number.',
    contacts: 'Only people who opted in may receive your offers.',
    templates: 'Every offer you start is an approved template.',
    campaigns: 'Reach a whole tagged group at once, now or on a schedule.',
    automations: 'Answer replies to your offers while you are busy.',
    team: 'Let colleagues follow up on the replies.',
  },
  support: {
    whatsapp: 'Customers reach you on the number they already know.',
    team: 'Share the inbox so no chat waits for one person.',
    automations: 'A welcome or away reply answers instantly, even after hours.',
    contacts: 'See who each customer is when they message.',
  },
}

const defaultWhy: Record<ChecklistStepId, string> = {
  whatsapp: 'Everything else sends and receives through this number.',
  products: 'Buyers pick from these in the chat.',
  payments: 'Buyers pay you directly.',
  store: 'Opens your shop to buyers on WhatsApp.',
  contacts: 'Your audience for offers and updates.',
  templates: 'Needed to start conversations with customers.',
  campaigns: 'Reach many opted-in customers at once.',
  automations: 'Saves typing the same answers again.',
  team: 'Share the work of replying.',
}

export function stepOrder(goals: Goals | undefined): readonly ChecklistStepId[] {
  const chosen = normalizeGoals(goals ?? [])
  if (chosen.length === 0) return DEFAULT_ORDER
  const order = [...chosen.flatMap((goal) => goalFirstSteps[goal]), ...chosen.flatMap((goal) => goalOrders[goal])]
  return [...new Set(order)]
}

export function stepWhy(goals: Goals | undefined, id: ChecklistStepId): string {
  for (const goal of normalizeGoals(goals ?? [])) {
    const why = goalWhy[goal][id]
    if (why) return why
  }
  return defaultWhy[id]
}

/** Step definitions in the goals' order, with the why-line. */
export function goalSteps(goals: Goals | undefined): (StepDefinition & { why: string })[] {
  return stepOrder(goals).map((id) => ({ ...stepDefinitions[id], why: stepWhy(goals, id) }))
}

export const goalOptions: readonly { value: WorkspaceGoal; title: string; description: string }[] = [
  { value: 'sell', title: 'Sell products on WhatsApp', description: 'Buyers browse, order and pay inside the chat.' },
  { value: 'marketing', title: 'Send offers and updates', description: 'Message opted-in customers with approved templates.' },
  { value: 'support', title: 'Reply to customers faster', description: 'A shared inbox with automatic replies.' },
]

export function goalLabel(goals: Goals | undefined): string {
  const titles = goalOptions.filter((option) => goals?.includes(option.value)).map((option) => option.title)
  return titles.length > 0 ? titles.join(', ') : 'Not chosen'
}
