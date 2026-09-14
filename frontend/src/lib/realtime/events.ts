/**
 * WebSocket frames from `docs/contracts/wave-2.md`. Payloads are thin: refetch via REST.
 * Server → client frame: `{ v: 1, type, workspace_id, data }`.
 */

import type { Schemas } from '../../api/types'

type MessageStatus = Schemas['MessageStatusEnum']
type CampaignStatus = Schemas['CampaignStatusEnum']

export type CampaignStats = Schemas['CampaignStats']

export type RealtimeEventMap = {
  'message.created': { conversation_id: string; message_id: string; direction: 'inbound' | 'outbound' }
  'message.status': { conversation_id: string; message_id: string; status: MessageStatus }
  'conversation.updated': { conversation_id: string }
  'campaign.progress': { campaign_id: string; status: CampaignStatus; stats: CampaignStats }
  'session.revoked': { reason: string }
}

export type RealtimeEventType = keyof RealtimeEventMap

export type RealtimeFrame<T extends RealtimeEventType = RealtimeEventType> = {
  [K in T]: { v: 1; type: K; workspace_id: string; data: RealtimeEventMap[K] }
}[T]

export const realtimeEventTypes: readonly RealtimeEventType[] = [
  'message.created',
  'message.status',
  'conversation.updated',
  'campaign.progress',
  'session.revoked',
]

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

/** Parses and validates the envelope of a server frame. Unknown types and versions are dropped. */
export function parseFrame(raw: unknown): RealtimeFrame | null {
  let value: unknown = raw
  if (typeof raw === 'string') {
    try {
      value = JSON.parse(raw)
    } catch {
      return null
    }
  }
  if (!isRecord(value) || value.v !== 1 || typeof value.workspace_id !== 'string' || !isRecord(value.data)) return null
  if (!realtimeEventTypes.includes(value.type as RealtimeEventType)) return null
  return value as RealtimeFrame
}
