import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { createWsTicket } from '../../api/realtime'
import { queryKeys } from '../../api/queryKeys'
import { env } from '../../config/env'
import { RealtimeConnection, type ConnectionStatus } from './connection'
import type { RealtimeEventType } from './events'
import { subscribe, type RealtimeHandler } from './registry'

/**
 * Subscribes to one realtime event type while the component is mounted.
 * The handler may change between renders without resubscribing.
 *
 * ```ts
 * useRealtimeEvent('message.created', ({ conversation_id }) => {
 *   queryClient.invalidateQueries({ queryKey: inboxKeys.detail(workspaceId, conversation_id) })
 * })
 * ```
 */
export function useRealtimeEvent<T extends RealtimeEventType>(type: T, handler: RealtimeHandler<T>) {
  const ref = useRef(handler)
  useEffect(() => {
    ref.current = handler
  })
  useEffect(() => subscribe(type, (data, frame) => ref.current(data, frame)), [type])
}

/**
 * Keeps one realtime connection for the workspace. In mock mode frames come from the mock emitter.
 * On reconnect every query of the workspace is invalidated. On `session.revoked` `onSessionRevoked` runs.
 */
export function useRealtimeConnection(workspaceId: string | undefined, onSessionRevoked: (reason: string) => void) {
  const queryClient = useQueryClient()
  const [status, setStatus] = useState<ConnectionStatus>('idle')
  const revokedRef = useRef(onSessionRevoked)
  useEffect(() => {
    revokedRef.current = onSessionRevoked
  })

  useEffect(() => {
    if (!workspaceId) return
    let stop: (() => void) | null = null
    let cancelled = false

    if (import.meta.env.VITE_API_MODE === 'mock') {
      void import('../../mocks/realtime').then(({ mockRealtime }) => {
        if (cancelled) return
        setStatus('open')
        stop = mockRealtime.connect(workspaceId, (reason) => revokedRef.current(reason))
      })
    } else {
      const connection = new RealtimeConnection({
        workspaceId,
        wsUrl: env.wsUrl,
        getTicket: createWsTicket,
        onStatusChange: setStatus,
        onReconnect: () => {
          void queryClient.invalidateQueries({ queryKey: queryKeys.workspace(workspaceId) })
        },
        onSessionRevoked: (reason) => revokedRef.current(reason),
      })
      connection.start()
      stop = () => connection.stop()
    }

    return () => {
      cancelled = true
      stop?.()
    }
  }, [workspaceId, queryClient])

  return status
}
