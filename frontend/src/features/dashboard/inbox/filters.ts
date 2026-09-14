import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router'
import type { ConversationStatus } from './api'

export type InboxView = 'open' | 'mine' | 'unassigned' | 'pending' | 'closed'

export const inboxViews: { value: InboxView; label: string }[] = [
  { value: 'open', label: 'Open' },
  { value: 'mine', label: 'Mine' },
  { value: 'unassigned', label: 'Unassigned' },
  { value: 'pending', label: 'Pending' },
  { value: 'closed', label: 'Closed' },
]

export type InboxFilters = {
  view: InboxView
  /** Business phone number id, or '' for all numbers. */
  number: string
  unread: boolean
  /** Contact name or phone. */
  q: string
}

/** Query params of `GET conversations/` for the filters. Mine and Unassigned show open conversations. */
export function conversationQuery(filters: InboxFilters) {
  const byView: Record<InboxView, { status: ConversationStatus; assignee?: string }> = {
    open: { status: 'open' },
    mine: { status: 'open', assignee: 'me' },
    unassigned: { status: 'open', assignee: 'none' },
    pending: { status: 'pending' },
    closed: { status: 'closed' },
  }
  return {
    ...byView[filters.view],
    phone_number: filters.number || undefined,
    unread: filters.unread || undefined,
    search: filters.q.trim() || undefined,
  }
}

function isView(value: string | null): value is InboxView {
  return inboxViews.some((view) => view.value === value)
}

/**
 * Inbox filters in the URL: `?view=mine&number=<id>&unread=1&q=priya`. Defaults are omitted.
 * Updates replace the history entry so filter changes don't fill the back stack.
 */
export function useInboxFilters() {
  const [params, setParams] = useSearchParams()

  const filters = useMemo<InboxFilters>(() => {
    const view = params.get('view')
    return {
      view: isView(view) ? view : 'open',
      number: params.get('number') ?? '',
      unread: params.get('unread') === '1',
      q: params.get('q') ?? '',
    }
  }, [params])

  const setFilters = useCallback(
    (patch: Partial<InboxFilters>) => {
      setParams(
        (current) => {
          const next = new URLSearchParams(current)
          const apply = (key: string, value: string | null) => (value ? next.set(key, value) : next.delete(key))
          if (patch.view !== undefined) apply('view', patch.view === 'open' ? null : patch.view)
          if (patch.number !== undefined) apply('number', patch.number || null)
          if (patch.unread !== undefined) apply('unread', patch.unread ? '1' : null)
          if (patch.q !== undefined) apply('q', patch.q.trim() ? patch.q : null)
          return next
        },
        { replace: true },
      )
    },
    [setParams],
  )

  return { filters, setFilters, search: params.toString() }
}
