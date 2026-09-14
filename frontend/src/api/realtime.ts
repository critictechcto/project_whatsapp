import { apiFetch, WORKSPACE_HEADER } from './client'
import type { Schemas } from './types'

/** Single-use ticket (`expires_in` seconds) for the WebSocket at `path` (`/ws/v1/`). */
export type WsTicket = Schemas['WsTicket']

export function createWsTicket(workspaceId: string): Promise<WsTicket> {
  return apiFetch<WsTicket>('/api/v1/inbox/ws-ticket/', {
    method: 'POST',
    headers: { [WORKSPACE_HEADER]: workspaceId },
  })
}
