import { useCallback } from 'react'
import { useQuery, useQueryClient, type InfiniteData, type QueryClient } from '@tanstack/react-query'
import { api, idempotencyHeaders, newIdempotencyKey, unwrap } from '../../../../api/client'
import { useCursorQuery } from '../../../../api/pagination'
import type { CursorPage } from '../../../../api/types'
import { useWorkspace } from '../../../../lib/workspace'
import { inboxKeys, toSendError, type Message, type MessageStatus, type MessageType, type SendError, type SendMessageRequest } from '../api'

type MessagePages = InfiniteData<CursorPage<Message>>

export const MESSAGE_PAGE_SIZE = 30

/** Messages of a conversation. Pages come newest first; the thread renders them reversed. */
export function useMessages(conversationId: string) {
  const { workspaceId } = useWorkspace()
  return useCursorQuery<Message>({
    queryKey: inboxKeys.messages(workspaceId, conversationId),
    queryFn: ({ cursor, signal }) =>
      unwrap(
        api.GET('/api/v1/inbox/conversations/{id}/messages/', {
          params: { path: { id: conversationId }, query: { cursor, page_size: MESSAGE_PAGE_SIZE } },
          signal,
        }),
      ),
  })
}

/** What an optimistic bubble shows before the server message exists. */
export type OutboxDisplay = {
  type: MessageType
  text: string
  templateName?: string
  fileName?: string
  mimeType?: string
  size?: number
}

/**
 * A send started in this tab. `key` is its Idempotency-Key, reused when the same send is retried.
 * Once the server answers, `serverId` links it to the real message; the entry is dropped when the
 * message appears in the thread, so a bubble never renders twice.
 */
export type OutboxEntry = {
  localId: string
  key: string
  conversationId: string
  request: SendMessageRequest
  display: OutboxDisplay
  state: 'sending' | 'sent' | 'failed'
  error?: SendError
  serverId?: string
  serverStatus?: MessageStatus
  createdAt: string
}

export function getOutbox(queryClient: QueryClient, workspaceId: string, conversationId: string): OutboxEntry[] {
  return queryClient.getQueryData<OutboxEntry[]>(inboxKeys.outbox(workspaceId, conversationId)) ?? []
}

export function updateOutbox(
  queryClient: QueryClient,
  workspaceId: string,
  conversationId: string,
  update: (entries: OutboxEntry[]) => OutboxEntry[],
) {
  queryClient.setQueryData<OutboxEntry[]>(inboxKeys.outbox(workspaceId, conversationId), (entries) => update(entries ?? []))
}

const emptyOutbox: OutboxEntry[] = []

/** Pending sends of a conversation. Lives in the query cache (never fetched) so it survives thread remounts. */
export function useOutbox(conversationId: string): OutboxEntry[] {
  const { workspaceId } = useWorkspace()
  const { data } = useQuery({
    queryKey: inboxKeys.outbox(workspaceId, conversationId),
    queryFn: () => emptyOutbox,
    initialData: emptyOutbox,
    enabled: false,
    staleTime: Infinity,
    gcTime: Infinity,
  })
  return data
}

/** Adds the server message to the newest page unless it is already loaded. */
export function insertMessage(queryClient: QueryClient, workspaceId: string, message: Message) {
  queryClient.setQueryData<MessagePages>(inboxKeys.messages(workspaceId, message.conversation_id), (data) => {
    if (!data || data.pages.length === 0) return data
    if (data.pages.some((page) => page.results.some((existing) => existing.id === message.id))) return data
    const [first, ...rest] = data.pages
    return { ...data, pages: [{ ...first, results: [message, ...first.results] }, ...rest] }
  })
}

/** Sets a message's status in the thread cache. Returns false when the message isn't loaded. */
export function patchMessageStatus(
  queryClient: QueryClient,
  workspaceId: string,
  conversationId: string,
  messageId: string,
  status: MessageStatus,
): boolean {
  let found = false
  queryClient.setQueryData<MessagePages>(inboxKeys.messages(workspaceId, conversationId), (data) => {
    if (!data) return data
    return {
      ...data,
      pages: data.pages.map((page) => {
        if (!page.results.some((message) => message.id === messageId)) return page
        found = true
        return { ...page, results: page.results.map((message) => (message.id === messageId ? { ...message, status } : message)) }
      }),
    }
  })
  if (!found) {
    updateOutbox(queryClient, workspaceId, conversationId, (entries) => {
      if (!entries.some((entry) => entry.serverId === messageId)) return entries
      found = true
      return entries.map((entry) => (entry.serverId === messageId ? { ...entry, serverStatus: status } : entry))
    })
  }
  return found
}

/** The newest loaded message of a conversation, if its thread is cached. */
export function newestCachedMessage(queryClient: QueryClient, workspaceId: string, conversationId: string): Message | undefined {
  return queryClient.getQueryData<MessagePages>(inboxKeys.messages(workspaceId, conversationId))?.pages[0]?.results[0]
}

/**
 * Sending with optimistic bubbles. `send` creates a new intent (new Idempotency-Key); `retry` repeats
 * a failed intent with the same key, so a request that did reach the server is not sent twice.
 */
export function useSendMessage(conversationId: string) {
  const { workspaceId } = useWorkspace()
  const queryClient = useQueryClient()

  const run = useCallback(
    async (entry: OutboxEntry) => {
      const patch = (changes: Partial<OutboxEntry>) =>
        updateOutbox(queryClient, workspaceId, conversationId, (entries) =>
          entries.map((current) => (current.localId === entry.localId ? { ...current, ...changes } : current)),
        )
      patch({ state: 'sending', error: undefined })
      try {
        const message = await unwrap(
          api.POST('/api/v1/inbox/conversations/{id}/messages/', {
            params: { path: { id: conversationId } },
            body: entry.request,
            headers: idempotencyHeaders(entry.key),
          }),
        )
        patch({ state: 'sent', serverId: message.id, serverStatus: message.status })
        insertMessage(queryClient, workspaceId, message)
        void queryClient.invalidateQueries({ queryKey: inboxKeys.messages(workspaceId, conversationId) })
        void queryClient.invalidateQueries({ queryKey: inboxKeys.lists(workspaceId) })
      } catch (error) {
        patch({ state: 'failed', error: toSendError(error) })
      }
    },
    [queryClient, workspaceId, conversationId],
  )

  const send = useCallback(
    (request: SendMessageRequest, display: OutboxDisplay) => {
      const entry: OutboxEntry = {
        localId: crypto.randomUUID(),
        key: newIdempotencyKey(),
        conversationId,
        request,
        display,
        state: 'sending',
        createdAt: new Date().toISOString(),
      }
      updateOutbox(queryClient, workspaceId, conversationId, (entries) => [...entries, entry])
      void run(entry)
    },
    [queryClient, workspaceId, conversationId, run],
  )

  const retry = useCallback(
    (localId: string) => {
      const entry = getOutbox(queryClient, workspaceId, conversationId).find((candidate) => candidate.localId === localId)
      if (entry && entry.state === 'failed') void run(entry)
    },
    [queryClient, workspaceId, conversationId, run],
  )

  const discard = useCallback(
    (localId: string) =>
      updateOutbox(queryClient, workspaceId, conversationId, (entries) => entries.filter((entry) => entry.localId !== localId)),
    [queryClient, workspaceId, conversationId],
  )

  return { send, retry, discard }
}
