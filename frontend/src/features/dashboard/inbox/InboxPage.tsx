import { useCallback, useMemo, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { MessagesSquare } from 'lucide-react'
import { useNavigate, useParams } from 'react-router'
import { Drawer } from '../../../components/app/Dialog'
import { cn } from '../../../lib/cn'
import { useWorkspace } from '../../../lib/workspace'
import { inboxKeys, type Conversation } from './api'
import { ConversationList } from './components/ConversationList'
import { DetailsPanel } from './components/DetailsPanel'
import { ShortcutsDialog } from './components/ShortcutsDialog'
import { StartConversationDialog } from './components/StartConversationDialog'
import { Thread } from './components/Thread'
import { useInboxFilters } from './filters'
import { findListedConversation, useConversation, useConversationList } from './hooks/conversations'
import { useNow } from './hooks/misc'
import { useInboxRealtime } from './hooks/realtime'
import { useInboxShortcuts } from './hooks/shortcuts'
import { COMPOSER_ID, contactName } from './utils'

/**
 * Team inbox at `inbox` and `inbox/:conversationId`: conversation list, thread and details.
 * Below `md` the list and the thread are separate screens; below `xl` details open in a drawer.
 */
export function InboxPage() {
  const { conversationId } = useParams()
  const { workspaceId, can } = useWorkspace()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { filters, setFilters, search } = useInboxFilters()
  const list = useConversationList(filters)
  const conversation = useConversation(conversationId)
  const now = useNow(15_000)
  const searchRef = useRef<HTMLInputElement>(null)

  const [drawerFor, setDrawerFor] = useState<string | null>(null)
  const [startOpen, setStartOpen] = useState(false)
  const [shortcutsOpen, setShortcutsOpen] = useState(false)
  const [announcement, setAnnouncement] = useState({ id: 0, text: '' })

  const hrefFor = useCallback(
    (id?: string) => `/app/w/${workspaceId}/inbox${id ? `/${id}` : ''}${search ? `?${search}` : ''}`,
    [workspaceId, search],
  )

  useInboxRealtime({
    onInbound: (id) => {
      const found = findListedConversation(queryClient, workspaceId, id) ?? queryClient.getQueryData<Conversation>(inboxKeys.detail(workspaceId, id))
      const text = `New message from ${found ? contactName(found.contact) : 'a customer'}`
      setAnnouncement((current) => ({ id: current.id + 1, text }))
    },
  })

  const ids = useMemo(() => list.items.map((item) => item.id), [list.items])
  useInboxShortcuts({
    ids,
    activeId: conversationId,
    onNavigate: (id) => navigate(hrefFor(id)),
    onFocusSearch: () => searchRef.current?.focus(),
    onFocusComposer: () => document.getElementById(COMPOSER_ID)?.focus(),
    onHelp: () => setShortcutsOpen(true),
  })

  const details = conversation.data

  return (
    <div className="-mx-4 -my-6 h-[calc(100dvh-3.5rem)] min-h-[28rem] sm:-mx-8 sm:-my-8 lg:h-dvh">
      <div className="flex h-full min-h-0 bg-card xl:border-x xl:border-line">
        <section
          aria-label="Conversation list"
          className={cn('min-h-0 w-full shrink-0 flex-col border-line bg-paper md:flex md:w-[300px] md:border-r', conversationId ? 'hidden' : 'flex')}
        >
          <ConversationList
            filters={filters}
            setFilters={setFilters}
            list={list}
            activeId={conversationId}
            hrefFor={hrefFor}
            now={now}
            canStart={can('agent')}
            onStart={() => setStartOpen(true)}
            searchRef={searchRef}
          />
        </section>

        <section aria-label="Conversation" className={cn('min-h-0 min-w-0 flex-1 flex-col md:flex', conversationId ? 'flex' : 'hidden')}>
          {conversationId ? (
            <Thread
              key={conversationId}
              conversationId={conversationId}
              backHref={hrefFor()}
              now={now}
              onOpenDetails={() => setDrawerFor(conversationId)}
            />
          ) : (
            <div className="grid h-full place-items-center bg-wallpaper/60 px-6 text-center">
              <div className="max-w-xs">
                <MessagesSquare className="mx-auto size-7 text-muted" aria-hidden="true" />
                <p className="mt-3 font-display text-base font-semibold text-ink">Pick a conversation</p>
                <p className="mt-1 text-[13px] text-muted">
                  Reply within 24 hours of a customer's message, or send an approved template. Press <kbd className="font-mono">?</kbd> for
                  shortcuts.
                </p>
              </div>
            </div>
          )}
        </section>

        {conversationId && details && (
          <aside aria-label="Conversation details" className="hidden w-[290px] shrink-0 overflow-y-auto border-l border-line bg-paper xl:block">
            <DetailsPanel conversation={details} now={now} onShowShortcuts={() => setShortcutsOpen(true)} />
          </aside>
        )}
      </div>

      <div aria-live="polite" className="sr-only">
        {announcement.text && <p key={announcement.id}>{announcement.text}</p>}
      </div>

      {details && (
        <Drawer
          open={drawerFor === conversationId}
          onOpenChange={(open) => setDrawerFor(open ? (conversationId ?? null) : null)}
          title="Details"
          width="max-w-sm"
        >
          <div className="-mx-5 -my-4">
            <DetailsPanel conversation={details} now={now} onShowShortcuts={() => setShortcutsOpen(true)} />
          </div>
        </Drawer>
      )}

      <StartConversationDialog open={startOpen} onOpenChange={setStartOpen} onStarted={(id) => navigate(hrefFor(id))} />
      <ShortcutsDialog open={shortcutsOpen} onOpenChange={setShortcutsOpen} />
    </div>
  )
}
