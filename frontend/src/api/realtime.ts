import { apiFetch, WORKSPACE_HEADER } from './client'

// TODO(wave-2): `POST /api/v1/inbox/ws-ticket/` is in docs/contracts/wave-2.md but not in openapi.yml yet.
// Replace with `unwrap(api.POST('/api/v1/inbox/ws-ticket/'))` and `Schemas['WsTicket']` after regenerating types.
export type WsTicket = {
  ticket: string
  /** Seconds until the single-use ticket expires. */
  expires_in: number
  /** WebSocket path, `/ws/v1/`. */
  path: string
}

export function createWsTicket(workspaceId: string): Promise<WsTicket> {
  return apiFetch<WsTicket>('/api/v1/inbox/ws-ticket/', {
    method: 'POST',
    headers: { [WORKSPACE_HEADER]: workspaceId },
  })
}
