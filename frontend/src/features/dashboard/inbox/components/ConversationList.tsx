import { memo, useEffect, useMemo, useRef, useState, type Ref } from 'react'
import { Clock, Inbox, Lock, MessageSquarePlus, Search } from 'lucide-react'
import { Link } from 'react-router'
import { Avatar } from '../../../../components/app/Avatar'
import { Button } from '../../../../components/app/Button'
import { initials } from '../../../../components/app/initials'
import { Input, Select } from '../../../../components/app/Input'
import { Skeleton } from '../../../../components/app/Spinner'
import { Tabs } from '../../../../components/app/Tabs'
import { cn } from '../../../../lib/cn'
import { useWorkspace } from '../../../../lib/workspace'
import type { Conversation } from '../api'
import { inboxViews, type InboxFilters } from '../filters'
import { usePhoneNumbers, type useConversationList } from '../hooks/conversations'
import {
  contactName,
  formatDurationShort,
  formatListTime,
  previewText,
  WINDOW_WARNING_MS,
  windowRemainingMs,
} from '../utils'
import { MessageTicks } from './MessageTicks'

type ConversationRowProps = {
  conversation: Conversation
  active: boolean
  href: string
  now: number
  timeZone: string
}

const ConversationRow = memo(function ConversationRow({ conversation, active, href, now, timeZone }: ConversationRowProps) {
  const name = contactName(conversation.contact)
  const last = conversation.last_message
  const unread = conversation.unread_count
  const remaining = windowRemainingMs(conversation, now)

  return (
    <li>
      <Link
        to={href}
        aria-current={active ? 'page' : undefined}
        data-conversation-id={conversation.id}
        className={cn(
          'flex gap-3 border-b border-line-2 px-3 py-2.5 outline-offset-[-2px] transition-colors',
          active ? 'bg-accent-soft/70' : 'hover:bg-ink/[0.03]',
        )}
      >
        <Avatar name={name} size="md" />
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline justify-between gap-2">
            <p className={cn('truncate text-[13.5px] text-ink', unread > 0 ? 'font-semibold' : 'font-medium')}>{name}</p>
            <time dateTime={last?.created_at ?? undefined} className="shrink-0 font-mono text-[11px] text-muted">
              {formatListTime(conversation.last_message_at, timeZone, now)}
            </time>
          </div>
          <div className="mt-0.5 flex items-center gap-1">
            {last?.direction === 'outbound' && <MessageTicks status={last.status} />}
            <p className={cn('min-w-0 flex-1 truncate text-[12.5px]', unread > 0 ? 'text-ink-2' : 'text-muted')}>
              {last ? previewText(last.type, last.text) : 'No messages yet'}
            </p>
            {unread > 0 && (
              <span className="grid h-5 min-w-5 shrink-0 place-items-center rounded-full bg-accent px-1.5 text-[11px] font-semibold text-white">
                {unread}
                <span className="sr-only"> unread</span>
              </span>
            )}
          </div>
          <div className="mt-1 flex items-center gap-2 text-[11px]">
            {remaining > 0 ? (
              <span className={cn('inline-flex items-center gap-1 font-mono', remaining < WINDOW_WARNING_MS ? 'text-amber' : 'text-accent-2')}>
                <Clock className="size-3" aria-hidden="true" />
                {formatDurationShort(remaining)}
                <span className="sr-only"> left in the 24-hour window</span>
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 font-mono text-muted">
                <Lock className="size-3" aria-hidden="true" />
                Window closed
              </span>
            )}
            <span className="ml-auto inline-flex items-center gap-1 text-muted">
              {conversation.assignee ? (
                <>
                  <span
                    aria-hidden="true"
                    className="grid size-5 place-items-center rounded-full bg-paper-2 text-[9px] font-semibold text-ink-2 ring-1 ring-line"
                    title={conversation.assignee.full_name}
                  >
                    {initials(conversation.assignee.full_name || conversation.assignee.email)}
                  </span>
                  <span className="sr-only">Assigned to {conversation.assignee.full_name}</span>
                </>
              ) : (
                <span>Unassigned</span>
              )}
            </span>
          </div>
        </div>
      </Link>
    </li>
  )
})

type ConversationListProps = {
  filters: InboxFilters
  setFilters: (patch: Partial<InboxFilters>) => void
  list: ReturnType<typeof useConversationList>
  activeId: string | undefined
  hrefFor: (id: string) => string
  now: number
  canStart: boolean
  onStart: () => void
  searchRef: Ref<HTMLInputElement>
}

const emptyCopy: Record<InboxFilters['view'], string> = {
  open: 'No open conversations. New customer messages will show up here.',
  mine: 'Nothing assigned to you right now.',
  unassigned: 'Every open conversation has an owner.',
  pending: 'No conversations waiting on the customer.',
  closed: 'No closed conversations yet.',
}

export function ConversationList({ filters, setFilters, list, activeId, hrefFor, now, canStart, onStart, searchRef }: ConversationListProps) {
  const { timeZone } = useWorkspace()
  const phones = usePhoneNumbers()

  // Debounced search: typing updates local text; the URL follows 300 ms later.
  const [searchText, setSearchText] = useState(filters.q)
  const [syncedQ, setSyncedQ] = useState(filters.q)
  if (filters.q !== syncedQ) {
    setSyncedQ(filters.q)
    setSearchText(filters.q)
  }
  useEffect(() => {
    if (searchText === syncedQ) return
    const timer = setTimeout(() => {
      setSyncedQ(searchText)
      setFilters({ q: searchText })
    }, 300)
    return () => clearTimeout(timer)
  }, [searchText, syncedQ, setFilters])

  const numberOptions = useMemo(() => {
    const options = new Map<string, string>()
    for (const phone of phones.data ?? []) options.set(phone.id, `${phone.verified_name || 'Number'} · ${phone.display_phone_number}`)
    for (const conversation of list.items) {
      const phone = conversation.phone_number
      if (!options.has(phone.id)) options.set(phone.id, `${phone.verified_name || 'Number'} · ${phone.display_phone_number}`)
    }
    if (filters.number && !options.has(filters.number)) options.set(filters.number, 'Selected number')
    return [...options].map(([value, label]) => ({ value, label }))
  }, [phones.data, list.items, filters.number])

  const scrollRef = useRef<HTMLDivElement>(null)
  const sentinelRef = useRef<HTMLDivElement>(null)
  const { hasNextPage, isFetchingNextPage, fetchNextPage } = list
  useEffect(() => {
    const sentinel = sentinelRef.current
    if (!sentinel || !hasNextPage || isFetchingNextPage || typeof IntersectionObserver === 'undefined') return
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) void fetchNextPage()
      },
      { root: scrollRef.current, rootMargin: '240px' },
    )
    observer.observe(sentinel)
    return () => observer.disconnect()
  }, [hasNextPage, isFetchingNextPage, fetchNextPage])

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between gap-2 px-3 pb-2 pt-3">
        <h1 className="font-display text-xl font-semibold tracking-[-0.02em] text-ink">Inbox</h1>
        {canStart && (
          <Button size="sm" variant="secondary" icon={<MessageSquarePlus className="size-4" aria-hidden="true" />} onClick={onStart}>
            New conversation
          </Button>
        )}
      </div>

      <div className="flex flex-col gap-2 px-3 pb-2">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted" aria-hidden="true" />
          <Input
            ref={searchRef}
            type="search"
            aria-label="Search conversations"
            placeholder="Search name or phone"
            value={searchText}
            onChange={(event) => setSearchText(event.target.value)}
            className="h-9 pl-8"
          />
        </div>
        <div className="flex items-center gap-2">
          {numberOptions.length > 1 && (
            <div className="min-w-0 flex-1">
              <Select
                aria-label="Business number"
                value={filters.number}
                onChange={(event) => setFilters({ number: event.target.value })}
                options={numberOptions}
                placeholder="All numbers"
                className="h-8 text-[13px]"
              />
            </div>
          )}
          <button
            type="button"
            aria-pressed={filters.unread}
            onClick={() => setFilters({ unread: !filters.unread })}
            className={cn(
              'ml-auto inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md border px-2.5 text-[13px] font-medium transition-colors',
              filters.unread ? 'border-accent bg-accent-soft text-accent-2' : 'border-line bg-card text-ink-2 hover:border-ink/30',
            )}
          >
            <span aria-hidden="true" className={cn('size-1.5 rounded-full', filters.unread ? 'bg-accent' : 'bg-muted/50')} />
            Unread only
          </button>
        </div>
      </div>

      <Tabs
        label="Conversation views"
        items={inboxViews}
        value={filters.view}
        onValueChange={(view) => setFilters({ view })}
        className="px-1 [&_[role=tab]]:h-9 [&_[role=tab]]:px-2.5 [&_[role=tab]]:text-[13px]"
      />

      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto">
        {list.isPending ? (
          <ul aria-label="Loading conversations" aria-busy="true">
            {Array.from({ length: 6 }, (_, i) => (
              <li key={i} className="flex gap-3 border-b border-line-2 px-3 py-3">
                <Skeleton className="size-9 rounded-full" />
                <div className="flex flex-1 flex-col gap-2">
                  <Skeleton className="h-3.5 w-2/3" />
                  <Skeleton className="h-3 w-full" />
                </div>
              </li>
            ))}
          </ul>
        ) : list.isError ? (
          <div className="px-4 py-10 text-center text-sm text-muted">
            <p>Couldn't load conversations.</p>
            <Button size="sm" variant="secondary" className="mt-3" onClick={() => void list.refetch()}>
              Try again
            </Button>
          </div>
        ) : list.items.length === 0 ? (
          <div className="flex flex-col items-center px-6 py-12 text-center">
            <Inbox className="size-6 text-muted" aria-hidden="true" />
            <p className="mt-3 text-sm text-muted">
              {filters.q || filters.unread || filters.number ? 'No conversations match these filters.' : emptyCopy[filters.view]}
            </p>
          </div>
        ) : (
          <>
            <ul aria-label="Conversations">
              {list.items.map((conversation) => (
                <ConversationRow
                  key={conversation.id}
                  conversation={conversation}
                  active={conversation.id === activeId}
                  href={hrefFor(conversation.id)}
                  now={now}
                  timeZone={timeZone}
                />
              ))}
            </ul>
            <div ref={sentinelRef} className="flex justify-center px-3 py-3">
              {hasNextPage && (
                <Button size="sm" variant="ghost" loading={isFetchingNextPage} onClick={() => void fetchNextPage()}>
                  Load more conversations
                </Button>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
