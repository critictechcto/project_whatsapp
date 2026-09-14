import { authFetch, getActiveWorkspaceId, WORKSPACE_HEADER } from '../../../api/client'
import { ApiError, errorMessage } from '../../../api/errors'
import { workspaceKeys } from '../../../api/queryKeys'
import type { Schemas } from '../../../api/types'
import { env } from '../../../config/env'
import { refreshAccessToken } from '../../../lib/auth/refresh'
import { tokenStore } from '../../../lib/auth/tokens'

export type Conversation = Schemas['Conversation']
export type Message = Schemas['Message']
export type MessageType = Schemas['MessageTypeEnum']
export type MessageOrder = Schemas['MessageOrder']
export type MessageStatus = Schemas['MessageStatusEnum']
export type ConversationStatus = Schemas['ConversationStatusEnum']
export type ConversationNote = Schemas['ConversationNote']
export type MediaAsset = Schemas['MediaAsset']
export type SendMessageRequest = Schemas['SendMessageRequest']
export type UserSummary = Schemas['UserSummary']

const keys = workspaceKeys('inbox')

/** Query keys of the inbox area. Everything starts with `['ws', workspaceId, 'inbox']`. */
export const inboxKeys = {
  all: keys.all,
  lists: keys.lists,
  list: (workspaceId: string, filters: object) => keys.list(workspaceId, filters),
  detail: keys.detail,
  messages: (workspaceId: string, conversationId: string) => keys.custom(workspaceId, 'messages', conversationId),
  notes: (workspaceId: string, conversationId: string) => keys.custom(workspaceId, 'notes', conversationId),
  /** Local, never fetched: optimistic sends of a conversation (see `useOutbox`). */
  outbox: (workspaceId: string, conversationId: string) => keys.custom(workspaceId, 'outbox', conversationId),
  members: (workspaceId: string) => keys.custom(workspaceId, 'members'),
  phoneNumbers: (workspaceId: string) => keys.custom(workspaceId, 'phone-numbers'),
  contacts: (workspaceId: string, search: string) => keys.custom(workspaceId, 'contacts', { search }),
}

export const conversationPath = '/api/v1/inbox/conversations/{id}/' as const

/** URL of a message's stored media (streams the file; needs auth headers, so fetch it as a blob). */
export function messageMediaPath(messageId: string) {
  return `/api/v1/inbox/messages/${messageId}/media/`
}

/** Fetches a message's media through the authenticated client. */
export async function fetchMessageMedia(messageId: string, signal?: AbortSignal): Promise<Blob> {
  const response = await authFetch(new Request(`${env.apiUrl}${messageMediaPath(messageId)}`, { signal }))
  if (!response.ok) throw await ApiError.fromResponse(response)
  return response.blob()
}

/* ---------- Send errors ---------- */

/** Friendly copy for the 409 codes of `POST conversations/{id}/messages/` (and a few others). */
export const sendErrorCopy: Record<string, string> = {
  whatsapp_not_connected: 'Connect a WhatsApp number to this workspace before sending messages.',
  phone_number_not_registered: "This business number isn't registered on the WhatsApp Business Platform yet, so it can't send.",
  outside_service_window:
    "The 24-hour customer service window has closed. WhatsApp only allows approved template messages until the customer writes again.",
  contact_opted_out: 'This contact has opted out, so messages to them are blocked.',
  marketing_opt_in_required: "Marketing templates need the contact's recorded opt-in. Use a utility template or record their opt-in first.",
  template_not_approved: "This template isn't approved by Meta yet. Choose an approved template.",
  quota_exceeded: "You've reached your plan's message limit. Upgrade the plan to keep sending.",
  insufficient_role: "Your role in this workspace can't send messages.",
  network_error: 'Could not reach the server. Check your connection and retry.',
}

export type SendError = { code: string; message: string }

export function toSendError(error: unknown): SendError {
  if (error instanceof ApiError) {
    return { code: error.code, message: sendErrorCopy[error.code] ?? errorMessage(error) }
  }
  if (error instanceof TypeError) return { code: 'network_error', message: sendErrorCopy.network_error }
  return { code: 'unknown', message: errorMessage(error) }
}

/* ---------- Media ---------- */

export type AttachmentKind = 'image' | 'video' | 'audio' | 'document'

const MB = 1024 * 1024

/** Media types and sizes accepted for outgoing messages, following the limits set by Meta. */
export const attachmentRules: { kind: AttachmentKind; mimeTypes: string[]; maxBytes: number; label: string }[] = [
  { kind: 'image', mimeTypes: ['image/jpeg', 'image/png'], maxBytes: 5 * MB, label: 'JPEG or PNG images up to 5 MB' },
  { kind: 'video', mimeTypes: ['video/mp4', 'video/3gpp'], maxBytes: 16 * MB, label: 'MP4 or 3GP videos up to 16 MB' },
  {
    kind: 'audio',
    mimeTypes: ['audio/aac', 'audio/amr', 'audio/mpeg', 'audio/mp4', 'audio/ogg'],
    maxBytes: 16 * MB,
    label: 'AAC, AMR, MP3, M4A or OGG audio up to 16 MB',
  },
  {
    kind: 'document',
    mimeTypes: [
      'application/pdf',
      'text/plain',
      'application/msword',
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      'application/vnd.ms-excel',
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      'application/vnd.ms-powerpoint',
      'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    ],
    maxBytes: 100 * MB,
    label: 'PDF, Word, Excel, PowerPoint or text documents up to 100 MB',
  },
]

export const attachmentAccept = attachmentRules.flatMap((rule) => rule.mimeTypes).join(',')

export function formatBytes(bytes: number): string {
  if (bytes >= MB) return `${(bytes / MB).toFixed(bytes % MB ? 1 : 0)} MB`
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`
  return `${bytes} B`
}

export type AttachmentCheck = { ok: true; kind: AttachmentKind } | { ok: false; reason: string }

export function validateAttachment(file: Pick<File, 'name' | 'type' | 'size'>): AttachmentCheck {
  const rule = attachmentRules.find((candidate) => candidate.mimeTypes.includes(file.type))
  if (!rule) {
    return {
      ok: false,
      reason: `${file.name} can't be sent on WhatsApp. Supported: JPEG/PNG images, MP4 videos, common audio formats and PDF or Office documents.`,
    }
  }
  if (file.size > rule.maxBytes) {
    return { ok: false, reason: `${file.name} is ${formatBytes(file.size)}. WhatsApp accepts ${rule.label}.` }
  }
  return { ok: true, kind: rule.kind }
}

type XhrResult = { status: number; body: unknown }

function xhrUpload(file: File, token: string | null, onProgress: (fraction: number) => void, signal?: AbortSignal) {
  return new Promise<XhrResult>((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${env.apiUrl}/api/v1/inbox/media/`)
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`)
    const workspaceId = getActiveWorkspaceId()
    if (workspaceId) xhr.setRequestHeader(WORKSPACE_HEADER, workspaceId)
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && event.total > 0) onProgress(event.loaded / event.total)
    }
    xhr.onload = () => {
      let body: unknown
      try {
        body = xhr.responseText ? JSON.parse(xhr.responseText) : null
      } catch {
        body = null
      }
      resolve({ status: xhr.status, body })
    }
    xhr.onerror = () => reject(new TypeError('Network request failed'))
    xhr.onabort = () => reject(new DOMException('Upload cancelled', 'AbortError'))
    signal?.addEventListener('abort', () => xhr.abort(), { once: true })
    const form = new FormData()
    form.append('file', file)
    xhr.send(form)
  })
}

/**
 * Multipart upload to `POST inbox/media/` with progress. Uses XHR (fetch has no upload progress),
 * with the same auth and workspace headers as the API client and one refresh-and-retry on 401.
 */
export async function uploadMedia(
  file: File,
  { onProgress, signal }: { onProgress: (fraction: number) => void; signal?: AbortSignal },
): Promise<MediaAsset> {
  if (!tokenStore.getAccess() && tokenStore.getRefresh()) {
    await refreshAccessToken(null).catch(() => undefined)
  }
  const sentWith = tokenStore.getAccess()
  let result = await xhrUpload(file, sentWith, onProgress, signal)
  if (result.status === 401 && tokenStore.getRefresh()) {
    const refreshed = await refreshAccessToken(sentWith).then(
      () => true,
      () => false,
    )
    if (refreshed) result = await xhrUpload(file, tokenStore.getAccess(), onProgress, signal)
  }
  if (result.status < 200 || result.status >= 300) throw new ApiError(result.status, result.body)
  onProgress(1)
  return result.body as MediaAsset
}
