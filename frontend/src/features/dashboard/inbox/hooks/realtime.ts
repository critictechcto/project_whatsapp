import { useQueryClient } from '@tanstack/react-query'
import { useRealtimeEvent } from '../../../../lib/realtime/hooks'
import { useWorkspace } from '../../../../lib/workspace'
import { inboxKeys } from '../api'
import { patchConversation } from './conversations'
import { getOutbox, newestCachedMessage, patchMessageStatus } from './thread'

/**
 * Keeps inbox caches in sync with realtime frames. Payloads are thin, so most events refetch.
 * `session.revoked` is handled by the workspace shell.
 */
export function useInboxRealtime({ onInbound }: { onInbound?: (conversationId: string) => void } = {}) {
  const { workspaceId } = useWorkspace()
  const queryClient = useQueryClient()

  useRealtimeEvent('message.created', ({ conversation_id, direction }) => {
    // While this tab is sending into the conversation, the send itself refetches the thread when it
    // settles; refetching now could show the server message next to its optimistic bubble.
    const sending = getOutbox(queryClient, workspaceId, conversation_id).some((entry) => entry.state === 'sending')
    if (!sending) void queryClient.invalidateQueries({ queryKey: inboxKeys.messages(workspaceId, conversation_id) })
    void queryClient.invalidateQueries({ queryKey: inboxKeys.detail(workspaceId, conversation_id) })
    void queryClient.invalidateQueries({ queryKey: inboxKeys.lists(workspaceId) })
    if (direction === 'inbound') onInbound?.(conversation_id)
  })

  useRealtimeEvent('message.status', ({ conversation_id, message_id, status }) => {
    const found = patchMessageStatus(queryClient, workspaceId, conversation_id, message_id, status)
    // Failures carry an error message that the frame doesn't include.
    if (!found || status === 'failed') {
      void queryClient.invalidateQueries({ queryKey: inboxKeys.messages(workspaceId, conversation_id) })
    }
    if (newestCachedMessage(queryClient, workspaceId, conversation_id)?.id === message_id) {
      patchConversation(queryClient, workspaceId, conversation_id, (conversation) =>
        conversation.last_message ? { ...conversation, last_message: { ...conversation.last_message, status } } : conversation,
      )
    }
  })

  useRealtimeEvent('conversation.updated', ({ conversation_id }) => {
    void queryClient.invalidateQueries({ queryKey: inboxKeys.detail(workspaceId, conversation_id) })
    void queryClient.invalidateQueries({ queryKey: inboxKeys.lists(workspaceId) })
  })
}
