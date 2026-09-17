import type { AreaRoute } from '../registry/types'

/**
 * Routes under /app/w/:workspaceId/. `inbox/:conversationId` is a child of `inbox` so the page (and
 * its list scroll position) stays mounted while moving between conversations.
 * Filters live in the URL: `?view=mine&number=<phone id>&unread=1&q=priya`.
 */
export const routes: AreaRoute[] = [
  {
    path: 'inbox',
    handle: { title: 'Inbox' },
    lazy: async () => ({ Component: (await import('./InboxPage')).InboxPage }),
    // The page reads `:conversationId` itself; `element: null` marks the children as intentionally empty.
    children: [
      { index: true, element: null },
      { path: ':conversationId', element: null },
    ],
  },
]
