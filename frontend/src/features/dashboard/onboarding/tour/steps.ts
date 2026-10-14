import type { Role } from '../../../../lib/roles'
import { visibleNav } from '../../registry'

/** One way to show a step: the sidebar item it points at (`data-tour` = nav item id) and its copy. */
export type TourTarget = { target: string; title: string; body: string }

/** A tour step; the first target the person can see is used, so the last step falls back to Settings. */
export type TourStep = { id: string; targets: TourTarget[] }

export const TOUR_STEPS: TourStep[] = [
  {
    id: 'inbox',
    targets: [
      {
        target: 'inbox',
        title: 'Inbox',
        body: 'Chats with customers on your WhatsApp number arrive here. You can reply freely within 24 hours of a customer’s last message and assign chats to your team.',
      },
    ],
  },
  {
    id: 'contacts',
    targets: [
      {
        target: 'contacts',
        title: 'Contacts',
        body: 'Add or import your customers and keep a record of who agreed to hear from you. Replies like STOP opt people out automatically.',
      },
    ],
  },
  {
    id: 'templates',
    targets: [
      {
        target: 'templates',
        title: 'Templates',
        body: 'Messages outside the 24-hour customer service window need a template approved by Meta. Create templates here and follow their review.',
      },
    ],
  },
  {
    id: 'campaigns',
    targets: [
      {
        target: 'campaigns',
        title: 'Campaigns',
        body: 'Send an approved template to contacts who opted in, now or on a schedule. Sending stays within the messaging limits Meta sets for your number.',
      },
    ],
  },
  {
    id: 'connect',
    targets: [
      {
        target: 'whatsapp',
        title: 'WhatsApp',
        body: 'Connect your business number through Meta’s Embedded Signup. The WhatsApp Business account stays in your business’s name.',
      },
      {
        target: 'settings',
        title: 'Settings',
        body: 'Workspace details and preferences live here. An admin or owner connects the workspace’s WhatsApp number.',
      },
    ],
  },
]

/** Screens where the sidebar is always on screen (`lg` in the shell); below it the nav is a closed drawer. */
export const LARGE_SCREEN_QUERY = '(min-width: 1024px)'

export type ResolvedStep = TourTarget & { id: string }

/**
 * The steps to show: those whose nav item the role can see. On large screens the sidebar is on
 * screen, so a step is also skipped when its item is not in the DOM; on small screens every step is
 * a centred card and the DOM is not consulted.
 */
export function resolveSteps(role: Role | undefined, largeScreen: boolean, root: ParentNode = document): ResolvedStep[] {
  const visible = new Set(visibleNav(role).flatMap((group) => group.items.map((item) => item.id)))
  const steps: ResolvedStep[] = []
  for (const step of TOUR_STEPS) {
    const option = step.targets.find(({ target }) => visible.has(target) && (!largeScreen || findTarget(target, root) !== null))
    if (option) steps.push({ ...option, id: step.id })
  }
  return steps
}

/** The sidebar element for a nav item, preferring one that is laid out (the drawer may hold a copy). */
export function findTarget(target: string, root: ParentNode = document): HTMLElement | null {
  const elements = Array.from(root.querySelectorAll<HTMLElement>(`[data-tour="${CSS.escape(target)}"]`))
  return elements.find((element) => element.getClientRects().length > 0) ?? elements[0] ?? null
}
