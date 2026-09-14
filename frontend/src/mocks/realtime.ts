import type { RealtimeEventMap, RealtimeEventType, RealtimeFrame } from '../lib/realtime/events'
import { dispatch } from '../lib/realtime/registry'

type Connection = { workspaceId: string; onRevoked: (reason: string) => void }

const connections = new Set<Connection>()

/**
 * Mock realtime emitter. Uses the same frame shape and registry as the real socket, so screens
 * subscribed with `useRealtimeEvent` behave identically. Mock handlers call `emit` after mutations:
 *
 * ```ts
 * mockRealtime.emit('message.status', { conversation_id, message_id, status: 'delivered' }, ctx.workspace.id, 800)
 * ```
 */
export const mockRealtime = {
  /** Used by `useRealtimeConnection` in mock mode. */
  connect(workspaceId: string, onRevoked: (reason: string) => void): () => void {
    const connection = { workspaceId, onRevoked }
    connections.add(connection)
    return () => {
      connections.delete(connection)
    }
  },

  isConnected(workspaceId: string): boolean {
    return [...connections].some((connection) => connection.workspaceId === workspaceId)
  },

  /** Sends a frame to connected clients of the workspace, optionally after `delayMs`. */
  emit<T extends RealtimeEventType>(type: T, data: RealtimeEventMap[T], workspaceId: string, delayMs = 0): void {
    const send = () => {
      const frame = { v: 1, type, workspace_id: workspaceId, data } as RealtimeFrame
      const targets = [...connections].filter(
        (connection) => type === 'session.revoked' || connection.workspaceId === workspaceId,
      )
      if (!targets.length) return
      dispatch(frame)
      if (type === 'session.revoked') {
        for (const connection of targets) {
          connections.delete(connection)
          connection.onRevoked((data as RealtimeEventMap['session.revoked']).reason)
        }
      }
    }
    if (delayMs > 0) setTimeout(send, delayMs)
    else send()
  },

  /** Test helper. */
  reset() {
    connections.clear()
  },
}
