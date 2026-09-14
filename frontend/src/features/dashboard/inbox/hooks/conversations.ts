import { useMutation, useQuery, useQueryClient, type InfiniteData, type QueryClient } from '@tanstack/react-query'
import { api, unwrap } from '../../../../api/client'
import { errorMessage } from '../../../../api/errors'
import { useCursorQuery } from '../../../../api/pagination'
import type { CursorPage } from '../../../../api/types'
import { useToast } from '../../../../components/app/toastContext'
import { useWorkspace } from '../../../../lib/workspace'
import { inboxKeys, type Conversation, type ConversationNote } from '../api'
import { conversationQuery, type InboxFilters } from '../filters'

type ConversationPages = InfiniteData<CursorPage<Conversation>>

export const CONVERSATION_PAGE_SIZE = 20

/** The conversation list for the current filters, newest activity first. */
export function useConversationList(filters: InboxFilters) {
  const { workspaceId } = useWorkspace()
  const query = conversationQuery(filters)
  return useCursorQuery<Conversation>({
    queryKey: inboxKeys.list(workspaceId, query),
    queryFn: ({ cursor, signal }) =>
      unwrap(
        api.GET('/api/v1/inbox/conversations/', {
          params: { query: { ...query, cursor, page_size: CONVERSATION_PAGE_SIZE } },
          signal,
        }),
      ),
  })
}

/** A conversation already loaded by any list query (used as placeholder while the detail loads). */
export function findListedConversation(queryClient: QueryClient, workspaceId: string, id: string): Conversation | undefined {
  for (const [, data] of queryClient.getQueriesData<ConversationPages>({ queryKey: inboxKeys.lists(workspaceId) })) {
    for (const page of data?.pages ?? []) {
      const found = page.results.find((conversation) => conversation.id === id)
      if (found) return found
    }
  }
  return undefined
}

/** Updates a conversation everywhere it is cached (detail and list rows). */
export function patchConversation(
  queryClient: QueryClient,
  workspaceId: string,
  id: string,
  update: (conversation: Conversation) => Conversation,
) {
  queryClient.setQueryData<Conversation>(inboxKeys.detail(workspaceId, id), (current) => (current ? update(current) : current))
  queryClient.setQueriesData<ConversationPages>({ queryKey: inboxKeys.lists(workspaceId) }, (data) => {
    if (!data || !data.pages.some((page) => page.results.some((conversation) => conversation.id === id))) return data
    return {
      ...data,
      pages: data.pages.map((page) => ({
        ...page,
        results: page.results.map((conversation) => (conversation.id === id ? update(conversation) : conversation)),
      })),
    }
  })
}

export function putConversation(queryClient: QueryClient, workspaceId: string, conversation: Conversation) {
  queryClient.setQueryData(inboxKeys.detail(workspaceId, conversation.id), conversation)
  patchConversation(queryClient, workspaceId, conversation.id, () => conversation)
}

export function useConversation(id: string | undefined) {
  const { workspaceId } = useWorkspace()
  const queryClient = useQueryClient()
  return useQuery<Conversation, Error, Conversation, ReturnType<typeof inboxKeys.detail>>({
    queryKey: inboxKeys.detail(workspaceId, id ?? ''),
    queryFn: ({ signal }) =>
      unwrap(api.GET('/api/v1/inbox/conversations/{id}/', { params: { path: { id: id ?? '' } }, signal })),
    enabled: Boolean(id),
    placeholderData: () => (id ? findListedConversation(queryClient, workspaceId, id) : undefined),
  })
}

type ConversationAction = 'assign' | 'close' | 'reopen'

function runAction(action: ConversationAction, id: string, assigneeId: string | null) {
  const params = { path: { id } }
  switch (action) {
    case 'assign':
      return unwrap(api.POST('/api/v1/inbox/conversations/{id}/assign/', { params, body: { assignee_id: assigneeId } }))
    case 'close':
      return unwrap(api.POST('/api/v1/inbox/conversations/{id}/close/', { params }))
    case 'reopen':
      return unwrap(api.POST('/api/v1/inbox/conversations/{id}/reopen/', { params }))
  }
}

const actionFailure: Record<ConversationAction, string> = {
  assign: 'Could not change the assignee',
  close: 'Could not close the conversation',
  reopen: 'Could not reopen the conversation',
}

/** Assign, close and reopen. Updates the caches from the response, then refetches lists (rows may move tabs). */
export function useConversationActions(id: string) {
  const { workspaceId } = useWorkspace()
  const queryClient = useQueryClient()
  const { toast } = useToast()

  return useMutation({
    mutationFn: ({ action, assigneeId = null }: { action: ConversationAction; assigneeId?: string | null }) =>
      runAction(action, id, assigneeId),
    onSuccess: (conversation) => {
      putConversation(queryClient, workspaceId, conversation)
      void queryClient.invalidateQueries({ queryKey: inboxKeys.lists(workspaceId) })
    },
    onError: (error, { action }) => {
      toast({ title: actionFailure[action], description: errorMessage(error), tone: 'error' })
    },
  })
}

/** `POST read/`: resets the unread count (and sends Meta a read receipt for the latest inbound). */
export function useMarkRead() {
  const { workspaceId } = useWorkspace()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => unwrap(api.POST('/api/v1/inbox/conversations/{id}/read/', { params: { path: { id } } })),
    onMutate: (id) => {
      patchConversation(queryClient, workspaceId, id, (conversation) => ({ ...conversation, unread_count: 0 }))
    },
    onSuccess: (conversation) => putConversation(queryClient, workspaceId, conversation),
    onError: () => {
      void queryClient.invalidateQueries({ queryKey: inboxKeys.all(workspaceId) })
    },
  })
}

export function useNotes(conversationId: string) {
  const { workspaceId } = useWorkspace()
  return useQuery({
    queryKey: inboxKeys.notes(workspaceId, conversationId),
    queryFn: ({ signal }) =>
      unwrap(
        api.GET('/api/v1/inbox/conversations/{id}/notes/', {
          params: { path: { id: conversationId }, query: { page_size: 100 } },
          signal,
        }),
      ),
    select: (page): ConversationNote[] => [...page.results].sort((a, b) => a.created_at.localeCompare(b.created_at)),
  })
}

export function useAddNote(conversationId: string) {
  const { workspaceId } = useWorkspace()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: string) =>
      unwrap(api.POST('/api/v1/inbox/conversations/{id}/notes/', { params: { path: { id: conversationId } }, body: { body } })),
    onSuccess: (note) => {
      queryClient.setQueryData<CursorPage<ConversationNote>>(inboxKeys.notes(workspaceId, conversationId), (page) =>
        page && !page.results.some((existing) => existing.id === note.id) ? { ...page, results: [...page.results, note] } : page,
      )
      void queryClient.invalidateQueries({ queryKey: inboxKeys.notes(workspaceId, conversationId) })
    },
  })
}

export function useMembers(enabled = true) {
  const { workspaceId } = useWorkspace()
  return useQuery({
    queryKey: inboxKeys.members(workspaceId),
    queryFn: ({ signal }) => unwrap(api.GET('/api/v1/workspaces/members/', { params: { query: { page_size: 200 } }, signal })),
    select: (page) => page.results,
    staleTime: 5 * 60_000,
    enabled,
  })
}

export function usePhoneNumbers() {
  const { workspaceId } = useWorkspace()
  return useQuery({
    queryKey: inboxKeys.phoneNumbers(workspaceId),
    queryFn: ({ signal }) => unwrap(api.GET('/api/v1/whatsapp/phone-numbers/', { params: { query: { page_size: 50 } }, signal })),
    select: (page) => page.results,
    staleTime: 5 * 60_000,
  })
}

export function useContactSearch(search: string, enabled: boolean) {
  const { workspaceId } = useWorkspace()
  return useQuery({
    queryKey: inboxKeys.contacts(workspaceId, search),
    queryFn: ({ signal }) =>
      unwrap(api.GET('/api/v1/contacts/', { params: { query: { search: search || undefined, page_size: 20 } }, signal })),
    select: (page) => page.results,
    enabled,
    placeholderData: (previous) => previous,
  })
}

/** `POST conversations/` (get-or-create with a contact). */
export function useStartConversation() {
  const { workspaceId } = useWorkspace()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (contactId: string) => unwrap(api.POST('/api/v1/inbox/conversations/', { body: { contact_id: contactId } })),
    onSuccess: (conversation) => {
      putConversation(queryClient, workspaceId, conversation)
      void queryClient.invalidateQueries({ queryKey: inboxKeys.lists(workspaceId) })
    },
  })
}
