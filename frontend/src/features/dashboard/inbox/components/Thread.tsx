import { Fragment, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, MessagesSquare, PanelRight } from 'lucide-react'
import { Link } from 'react-router'
import { Avatar } from '../../../../components/app/Avatar'
import { Button } from '../../../../components/app/Button'
import { EmptyState } from '../../../../components/app/PageHeader'
import { Skeleton } from '../../../../components/app/Spinner'
import { StatusBadge } from '../../../../components/app/StatusBadge'
import { buttonClasses } from '../../../../components/app/styles'
import { cn } from '../../../../lib/cn'
import { useWorkspace } from '../../../../lib/workspace'
import type { Conversation, ConversationNote, Message } from '../api'
import { useConversation, useConversationActions, useMarkRead, useNotes } from '../hooks/conversations'
import { useDocumentVisible } from '../hooks/misc'
import { updateOutbox, useMessages, useOutbox, useSendMessage, type OutboxEntry } from '../hooks/thread'
import { contactName, dayKey, dayLabel, formatPhone } from '../utils'
import { Composer } from './Composer'
import { MessageBubble, NoteCard, PendingBubble } from './MessageBubble'
import { TemplateDialog } from './TemplateDialog'

type TimelineItem =
  | { kind: 'message'; key: string; at: number; iso: string; message: Message }
  | { kind: 'note'; key: string; at: number; iso: string; note: ConversationNote }
  | { kind: 'pending'; key: string; at: number; iso: string; entry: OutboxEntry }

function ThreadHeader({ conversation, backHref, onOpenDetails }: { conversation: Conversation; backHref: string; onOpenDetails: () => void }) {
  const { can } = useWorkspace()
  const actions = useConversationActions(conversation.id)
  const name = contactName(conversation.contact)
  const closed = conversation.status === 'closed'

  return (
    <header className="flex items-center gap-2 border-b border-line bg-card px-2 py-2 sm:px-4">
      <Link to={backHref} aria-label="Back to conversations" className={buttonClasses('ghost', 'icon-sm', 'md:hidden')}>
        <ArrowLeft className="size-4" aria-hidden="true" />
      </Link>
      <Avatar name={name} size="sm" />
      <div className="min-w-0 flex-1">
        <h2 className="truncate text-sm font-semibold text-ink">{name}</h2>
        <p className="truncate font-mono text-[11px] text-muted">
          {formatPhone(conversation.contact.phone_e164)} · via {conversation.phone_number.verified_name || conversation.phone_number.display_phone_number}
        </p>
      </div>
      <StatusBadge status={conversation.status} className="hidden sm:inline-flex" />
      {can('agent') && (
        <Button
          size="sm"
          variant="secondary"
          loading={actions.isPending}
          onClick={() => actions.mutate({ action: closed ? 'reopen' : 'close' })}
        >
          {closed ? 'Reopen' : 'Close'}
        </Button>
      )}
      <Button variant="ghost" size="icon-sm" aria-label="Conversation details" className="xl:hidden" onClick={onOpenDetails}>
        <PanelRight className="size-4" aria-hidden="true" />
      </Button>
    </header>
  )
}

function MessageStream({
  conversation,
  now,
  onUseTemplate,
  sender,
}: {
  conversation: Conversation
  now: number
  onUseTemplate: () => void
  sender: ReturnType<typeof useSendMessage>
}) {
  const { workspaceId, timeZone, can } = useWorkspace()
  const queryClient = useQueryClient()
  const messages = useMessages(conversation.id)
  const notes = useNotes(conversation.id)
  const outbox = useOutbox(conversation.id)
  const name = contactName(conversation.contact)
  const canSend = can('agent')

  const byId = useMemo(() => new Map(messages.items.map((message) => [message.id, message])), [messages.items])

  const items = useMemo<TimelineItem[]>(() => {
    const ordered = [...messages.items].reverse()
    // Notes older than the oldest loaded message appear once older pages load.
    const oldest = messages.hasNextPage && ordered[0] ? new Date(ordered[0].created_at).getTime() : -Infinity
    const timeline: TimelineItem[] = [
      ...ordered.map((message) => ({
        kind: 'message' as const,
        key: message.id,
        at: new Date(message.created_at).getTime(),
        iso: message.created_at,
        message,
      })),
      ...(notes.data ?? [])
        .map((note) => ({ kind: 'note' as const, key: `note-${note.id}`, at: new Date(note.created_at).getTime(), iso: note.created_at, note }))
        .filter((note) => note.at >= oldest),
    ].sort((a, b) => a.at - b.at)
    const pending = outbox
      .filter((entry) => !(entry.serverId && byId.has(entry.serverId)))
      .map((entry) => ({ kind: 'pending' as const, key: `pending-${entry.localId}`, at: new Date(entry.createdAt).getTime(), iso: entry.createdAt, entry }))
    return [...timeline, ...pending]
  }, [messages.items, messages.hasNextPage, notes.data, outbox, byId])

  // One "View order" link per order (on its earliest loaded message), plus one on each failed
  // message of an order so a failed buyer update leads straight to the order.
  const orderLinkIds = useMemo(() => {
    const seen = new Set<string>()
    const linked = new Set<string>()
    for (const message of [...messages.items].reverse()) {
      if (!message.order_id) continue
      if (!seen.has(message.order_id) || message.status === 'failed') linked.add(message.id)
      seen.add(message.order_id)
    }
    return linked
  }, [messages.items])

  // Drop optimistic entries once their server message is in the thread.
  useEffect(() => {
    if (!outbox.some((entry) => entry.serverId && byId.has(entry.serverId))) return
    updateOutbox(queryClient, workspaceId, conversation.id, (entries) => entries.filter((entry) => !(entry.serverId && byId.has(entry.serverId))))
  }, [outbox, byId, queryClient, workspaceId, conversation.id])

  // Scroll: start at the bottom, follow new messages when already near the bottom, and keep the
  // visible messages in place when older pages are prepended.
  const scrollRef = useRef<HTMLDivElement>(null)
  const anchorRef = useRef<{ height: number; top: number } | null>(null)
  const nearBottomRef = useRef(true)
  const edgesRef = useRef<{ first?: string; last?: string }>({})
  const firstKey = items[0]?.key
  const lastItem = items[items.length - 1]
  const lastKey = lastItem?.key

  useLayoutEffect(() => {
    const el = scrollRef.current
    if (!el) return
    const previous = edgesRef.current
    if (anchorRef.current && firstKey !== previous.first) {
      el.scrollTop = el.scrollHeight - anchorRef.current.height + anchorRef.current.top
      anchorRef.current = null
    } else if (lastKey !== previous.last && (nearBottomRef.current || lastItem?.kind === 'pending')) {
      el.scrollTop = el.scrollHeight
    }
    edgesRef.current = { first: firstKey, last: lastKey }
  }, [firstKey, lastKey, lastItem?.kind])

  const { hasNextPage, isFetchingNextPage, fetchNextPage } = messages
  const loadOlder = useCallback(() => {
    const el = scrollRef.current
    if (!hasNextPage || isFetchingNextPage) return
    if (el) anchorRef.current = { height: el.scrollHeight, top: el.scrollTop }
    void fetchNextPage()
  }, [hasNextPage, isFetchingNextPage, fetchNextPage])

  const onScroll = () => {
    const el = scrollRef.current
    if (!el) return
    nearBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 96
    if (el.scrollTop < 120) loadOlder()
  }

  const retryFailed = useCallback(
    (message: Message) =>
      sender.send({ type: 'text', text: message.text, preview_url: false }, { type: 'text', text: message.text }),
    [sender],
  )

  return (
    <div
      ref={scrollRef}
      onScroll={onScroll}
      role="region"
      aria-label={`Messages with ${name}`}
      tabIndex={0}
      className="min-h-0 flex-1 overflow-y-auto bg-wallpaper px-3 py-3 focus-visible:outline-offset-[-2px] sm:px-5"
    >
      {messages.isPending ? (
        <div className="flex flex-col gap-3" aria-busy="true" aria-label="Loading messages">
          <Skeleton className="h-12 w-2/3 rounded-lg bg-white/70" />
          <Skeleton className="ml-auto h-10 w-1/2 rounded-lg bg-bubble/70" />
          <Skeleton className="h-16 w-3/5 rounded-lg bg-white/70" />
        </div>
      ) : messages.isError ? (
        <div className="py-10 text-center text-sm text-muted">
          <p>Couldn't load messages.</p>
          <Button size="sm" variant="secondary" className="mt-3" onClick={() => void messages.refetch()}>
            Try again
          </Button>
        </div>
      ) : (
        <>
          <div className="flex justify-center pb-2">
            {hasNextPage ? (
              <Button size="sm" variant="secondary" loading={isFetchingNextPage} onClick={loadOlder}>
                Load older messages
              </Button>
            ) : (
              items.length > 0 && <p className="font-mono text-[11px] text-muted">Start of conversation</p>
            )}
          </div>
          {items.length === 0 && (
            <p className="py-10 text-center text-sm text-muted">No messages yet. Start with an approved template.</p>
          )}
          <ol className="isolate flex flex-col gap-1.5">
            {items.map((item, index) => {
              const showDay = index === 0 || dayKey(item.iso, timeZone) !== dayKey(items[index - 1].iso, timeZone)
              return (
                <Fragment key={item.key}>
                  {showDay && (
                    // Every day chip sticks in the same list, so older chips pile up under the newest one:
                    // later chips stack higher, and an opaque chip with a shared minimum width hides the rest.
                    <li className="sticky top-0 flex justify-center py-1.5" style={{ zIndex: 10 + index }}>
                      <span className="min-w-36 rounded-md bg-card px-2.5 py-1 text-center font-mono text-[11px] text-muted shadow-[0_1px_0_rgba(16,39,31,0.08)]">
                        {dayLabel(item.iso, timeZone, now)}
                      </span>
                    </li>
                  )}
                  <li
                    data-message-id={item.kind === 'message' ? item.message.id : item.kind === 'pending' ? (item.entry.serverId ?? item.entry.localId) : undefined}
                    className={cn(item.kind === 'note' && 'py-1')}
                  >
                    {item.kind === 'message' ? (
                      <MessageBubble
                        message={item.message}
                        replyTo={item.message.reply_to_message_id ? byId.get(item.message.reply_to_message_id) : undefined}
                        contactName={name}
                        timeZone={timeZone}
                        onRetry={canSend && item.message.type === 'text' && item.message.status === 'failed' ? retryFailed : undefined}
                        orderHref={
                          item.message.order_id && orderLinkIds.has(item.message.id)
                            ? `/app/w/${workspaceId}/orders/${item.message.order_id}`
                            : undefined
                        }
                      />
                    ) : item.kind === 'note' ? (
                      <NoteCard note={item.note} timeZone={timeZone} />
                    ) : (
                      <PendingBubble
                        entry={item.entry}
                        timeZone={timeZone}
                        onRetry={sender.retry}
                        onDiscard={sender.discard}
                        onUseTemplate={onUseTemplate}
                      />
                    )}
                  </li>
                </Fragment>
              )
            })}
          </ol>
        </>
      )}
    </div>
  )
}

type ThreadProps = {
  conversationId: string
  backHref: string
  now: number
  onOpenDetails: () => void
}

/** Header, message stream and composer of one conversation. Remount per conversation (`key`). */
export function Thread({ conversationId, backHref, now, onOpenDetails }: ThreadProps) {
  const { can } = useWorkspace()
  const conversation = useConversation(conversationId)
  const sender = useSendMessage(conversationId)
  const [templateOpen, setTemplateOpen] = useState(false)
  const { mutate: markRead } = useMarkRead()
  const visible = useDocumentVisible()
  const readTokenRef = useRef<string | null>(null)
  const data = conversation.data

  // Mark read when the thread is open and visible and has unread messages (agents and up).
  useEffect(() => {
    if (!data || !visible || data.unread_count === 0 || !can('agent')) return
    const token = `${data.id}:${data.unread_count}:${data.last_message_at}`
    if (readTokenRef.current === token) return
    readTokenRef.current = token
    markRead(data.id)
  }, [data, visible, can, markRead])

  if (!data) {
    if (conversation.isError) {
      return (
        <div className="grid h-full place-items-center p-6">
          <EmptyState
            icon={<MessagesSquare />}
            title="Conversation not found"
            description="It may have been removed, or the link is from another workspace."
            action={
              <Link to={backHref} className={buttonClasses('secondary')}>
                Back to conversations
              </Link>
            }
          />
        </div>
      )
    }
    return (
      <div className="flex h-full flex-col" aria-busy="true">
        <div className="flex items-center gap-3 border-b border-line px-4 py-3">
          <Skeleton className="size-7 rounded-full" />
          <Skeleton className="h-4 w-40" />
        </div>
        <div className="flex-1 bg-wallpaper" />
      </div>
    )
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <ThreadHeader conversation={data} backHref={backHref} onOpenDetails={onOpenDetails} />
      <MessageStream conversation={data} now={now} sender={sender} onUseTemplate={() => setTemplateOpen(true)} />
      <Composer conversation={data} now={now} send={sender.send} onOpenTemplate={() => setTemplateOpen(true)} />
      {can('agent') && <TemplateDialog open={templateOpen} onOpenChange={setTemplateOpen} conversation={data} onSend={sender.send} />}
    </div>
  )
}
