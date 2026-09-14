import { HttpResponse } from 'msw'
import { db } from '../../../mocks/db'
import { ids } from '../../../mocks/seed'
import { mockRealtime } from '../../../mocks/realtime'
import { authorize, errorResponse, http, mockDelay, notFound, nowIso, paginate, uuid, validationError } from '../../../mocks/utils'
import type { AreaMockHandlers } from '../registry/types'
import { validateAttachment, type Message, type MessageStatus } from './api'
import {
  contactIndexFromId,
  inboxState,
  mainNumber,
  mediaUrl,
  placeholderAudio,
  placeholderDocument,
  placeholderImage,
  replyPool,
  seedContact,
  statusTimes,
  templateBody,
  toConversation,
  unregisteredNumbers,
  userSummary,
  wamidFor,
  wholesaleNumber,
  type InboxMockState,
  type MockConversation,
  type MockMessage,
} from './mockData'

const DAY = 86_400_000

function findConversation(state: InboxMockState, workspaceId: string, id: string) {
  return state.conversations.find((conversation) => conversation.id === id && conversation.workspace_id === workspaceId)
}

function windowOpen(conversation: MockConversation) {
  return Boolean(conversation.last_inbound_at && Date.parse(conversation.last_inbound_at) + DAY > Date.now())
}

function conflict(code: string, message: string) {
  return errorResponse(409, code, message)
}

function emitUpdated(workspaceId: string, conversationId: string) {
  mockRealtime.emit('conversation.updated', { conversation_id: conversationId }, workspaceId)
}

/**
 * In mock mode (not tests), a sent message moves sent → delivered → read over a few seconds,
 * and every third send gets a customer reply.
 */
function simulateDelivery(state: InboxMockState, workspaceId: string, conversation: MockConversation, message: MockMessage, sendNumber: number) {
  if (import.meta.env.MODE === 'test') return
  const createdMs = Date.parse(message.created_at)
  const advance = (status: MessageStatus, delay: number) =>
    setTimeout(() => {
      if (message.status === 'failed') return
      Object.assign(message, { status }, statusTimes(status, createdMs))
      mockRealtime.emit('message.status', { conversation_id: conversation.id, message_id: message.id, status }, workspaceId)
    }, delay)

  advance('sent', 800)
  advance('delivered', 1800)
  if (sendNumber % 4 !== 0) advance('read', 3500)

  if (sendNumber % 3 === 0) {
    setTimeout(() => {
      const reply: MockMessage = {
        id: uuid(),
        conversation_id: conversation.id,
        direction: 'inbound',
        type: 'text',
        text: replyPool[sendNumber % replyPool.length],
        status: 'received',
        source: 'inbound',
        error_code: '',
        error_message: '',
        template: null,
        media: null,
        reply_to_message_id: null,
        sent_by: null,
        wamid: '',
        created_at: nowIso(),
        sent_at: null,
        delivered_at: null,
        read_at: null,
        failed_at: null,
      }
      reply.wamid = wamidFor(reply.id)
      state.messages.get(conversation.id)?.push(reply)
      conversation.unread_count += 1
      conversation.last_inbound_at = reply.created_at
      conversation.updated_at = reply.created_at
      if (conversation.status !== 'open') conversation.status = 'open'
      mockRealtime.emit('message.created', { conversation_id: conversation.id, message_id: reply.id, direction: 'inbound' }, workspaceId)
      emitUpdated(workspaceId, conversation.id)
    }, 5200)
  }
}

function mediaKind(mimeType: string): Message['type'] {
  if (mimeType.startsWith('image/')) return 'image'
  if (mimeType.startsWith('video/')) return 'video'
  if (mimeType.startsWith('audio/')) return 'audio'
  return 'document'
}

export const handlers: AreaMockHandlers = [
  http.get('/api/v1/inbox/conversations/', async ({ request, query, response }) => {
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    await mockDelay()
    const state = inboxState()
    const status = query.get('status')
    const assignee = query.get('assignee')
    const phoneNumber = query.get('phone_number')
    const unread = query.get('unread')
    const search = (query.get('search') ?? '').trim().toLowerCase()
    const digits = search.replace(/\D/g, '')

    const items = state.conversations
      .filter((conversation) => conversation.workspace_id === ctx.workspace.id)
      .filter((conversation) => !status || conversation.status === status)
      .filter((conversation) => {
        if (!assignee) return true
        if (assignee === 'me') return conversation.assignee_id === ctx.user.id
        if (assignee === 'none') return conversation.assignee_id === null
        return conversation.assignee_id === assignee
      })
      .filter((conversation) => !phoneNumber || conversation.phone_number.id === phoneNumber)
      .filter((conversation) => unread !== 'true' || conversation.unread_count > 0)
      .filter(
        (conversation) =>
          !search ||
          conversation.contact.name.toLowerCase().includes(search) ||
          (digits.length > 0 && conversation.contact.phone_e164.includes(digits)),
      )
      .map((conversation) => toConversation(state, conversation))
      .sort((a, b) => (b.last_message_at ?? b.created_at).localeCompare(a.last_message_at ?? a.created_at))

    return response(200).json(paginate(request, items, 20))
  }),

  http.post('/api/v1/inbox/conversations/', async ({ request, response }) => {
    const ctx = authorize(request, 'agent')
    if (ctx instanceof Response) return response.untyped(ctx)
    await mockDelay()
    const body = await request.json()
    if (ctx.workspace.id !== ids.sharmaSweets) {
      return response.untyped(conflict('whatsapp_not_connected', 'Connect a WhatsApp number to this workspace first.'))
    }
    if (!body.contact_id) return response.untyped(validationError({ contact_id: ['This field is required.'] }))
    const number = [mainNumber, wholesaleNumber].find((candidate) => candidate.id === (body.phone_number_id ?? mainNumber.id))
    if (!number) return response.untyped(validationError({ phone_number_id: ['Unknown phone number.'] }))

    const state = inboxState()
    const existing = state.conversations.find(
      (conversation) =>
        conversation.workspace_id === ctx.workspace.id &&
        conversation.contact.id === body.contact_id &&
        conversation.phone_number.id === number.id,
    )
    if (existing) return response(200).json(toConversation(state, existing))

    const index = contactIndexFromId(body.contact_id)
    const contact =
      index === null
        ? { id: body.contact_id, name: '', phone_e164: `+9170000${String(state.conversations.length).padStart(5, '0')}`, marketing_opt_in_status: 'unknown' as const }
        : seedContact(index)
    const conversation: MockConversation = {
      id: uuid(),
      workspace_id: ctx.workspace.id,
      contact,
      phone_number: number,
      status: 'open',
      assignee_id: null,
      unread_count: 0,
      last_inbound_at: null,
      created_at: nowIso(),
      updated_at: nowIso(),
    }
    state.conversations.push(conversation)
    state.messages.set(conversation.id, [])
    state.notes.set(conversation.id, [])
    emitUpdated(ctx.workspace.id, conversation.id)
    return response(201).json(toConversation(state, conversation))
  }),

  http.get('/api/v1/inbox/conversations/{id}/', async ({ request, params, response }) => {
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    await mockDelay(150)
    const state = inboxState()
    const conversation = findConversation(state, ctx.workspace.id, params.id)
    return conversation ? response(200).json(toConversation(state, conversation)) : response.untyped(notFound())
  }),

  http.post('/api/v1/inbox/conversations/{id}/assign/', async ({ request, params, response }) => {
    const ctx = authorize(request, 'agent')
    if (ctx instanceof Response) return response.untyped(ctx)
    await mockDelay()
    const state = inboxState()
    const conversation = findConversation(state, ctx.workspace.id, params.id)
    if (!conversation) return response.untyped(notFound())
    const body = await request.json()
    const assigneeId = body.assignee_id ?? null
    const isMember = (userId: string) =>
      db.memberships.some((membership) => membership.workspace_id === ctx.workspace.id && membership.user_id === userId)
    if (assigneeId && !isMember(assigneeId)) {
      return response.untyped(validationError({ assignee_id: ['Choose a member of this workspace.'] }))
    }
    conversation.assignee_id = assigneeId
    conversation.updated_at = nowIso()
    emitUpdated(ctx.workspace.id, conversation.id)
    return response(200).json(toConversation(state, conversation))
  }),

  http.post('/api/v1/inbox/conversations/{id}/close/', async ({ request, params, response }) => {
    const ctx = authorize(request, 'agent')
    if (ctx instanceof Response) return response.untyped(ctx)
    await mockDelay()
    const state = inboxState()
    const conversation = findConversation(state, ctx.workspace.id, params.id)
    if (!conversation) return response.untyped(notFound())
    conversation.status = 'closed'
    conversation.updated_at = nowIso()
    emitUpdated(ctx.workspace.id, conversation.id)
    return response(200).json(toConversation(state, conversation))
  }),

  http.post('/api/v1/inbox/conversations/{id}/reopen/', async ({ request, params, response }) => {
    const ctx = authorize(request, 'agent')
    if (ctx instanceof Response) return response.untyped(ctx)
    await mockDelay()
    const state = inboxState()
    const conversation = findConversation(state, ctx.workspace.id, params.id)
    if (!conversation) return response.untyped(notFound())
    conversation.status = 'open'
    conversation.updated_at = nowIso()
    emitUpdated(ctx.workspace.id, conversation.id)
    return response(200).json(toConversation(state, conversation))
  }),

  http.post('/api/v1/inbox/conversations/{id}/read/', async ({ request, params, response }) => {
    const ctx = authorize(request, 'agent')
    if (ctx instanceof Response) return response.untyped(ctx)
    await mockDelay(100)
    const state = inboxState()
    const conversation = findConversation(state, ctx.workspace.id, params.id)
    if (!conversation) return response.untyped(notFound())
    conversation.unread_count = 0
    return response(200).json(toConversation(state, conversation))
  }),

  http.get('/api/v1/inbox/conversations/{id}/messages/', async ({ request, params, response }) => {
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    await mockDelay()
    const state = inboxState()
    const conversation = findConversation(state, ctx.workspace.id, params.id)
    if (!conversation) return response.untyped(notFound())
    const newestFirst = [...(state.messages.get(conversation.id) ?? [])].reverse()
    return response(200).json(paginate(request, newestFirst, 30))
  }),

  http.post('/api/v1/inbox/conversations/{id}/messages/', async ({ request, params, response }) => {
    const ctx = authorize(request, 'agent')
    if (ctx instanceof Response) return response.untyped(ctx)
    await mockDelay(400)
    const state = inboxState()
    const conversation = findConversation(state, ctx.workspace.id, params.id)
    if (!conversation) return response.untyped(notFound())

    // Same Idempotency-Key: return the original message instead of sending again.
    const key = request.headers.get('Idempotency-Key')
    const idempotencyKey = key ? `${ctx.workspace.id}:${key}` : null
    if (idempotencyKey && state.idempotency.has(idempotencyKey)) {
      const original = state.messages.get(conversation.id)?.find((candidate) => candidate.id === state.idempotency.get(idempotencyKey))
      if (original) return response(201).json(original)
    }

    const body = await request.json()
    let type: Message['type'] = 'text'
    let text: string
    let template: Message['template'] = null
    let media: Message['media'] = null
    let blob: Blob | undefined

    if (body.type === 'text') {
      text = (body.text ?? '').trim()
      if (!text) return response.untyped(validationError({ text: ['This field is required.'] }))
      if (text.length > 4096) return response.untyped(validationError({ text: ['Ensure this field has no more than 4096 characters.'] }))
    } else if (body.type === 'template') {
      const rendered = body.template_id ? templateBody(body.template_id, body.body_params) : null
      if (!rendered) return response.untyped(validationError({ template_id: ['Choose a template.'] }))
      type = 'template'
      text = rendered.text
      template = { id: rendered.template.id, name: rendered.template.name, language: rendered.template.language }
    } else if (body.type === 'media') {
      const upload = body.media_id ? state.uploads.get(body.media_id) : undefined
      if (!upload || upload.workspaceId !== ctx.workspace.id) {
        return response.untyped(validationError({ media_id: ['Upload the file first.'] }))
      }
      type = mediaKind(upload.asset.mime_type)
      text = type === 'audio' ? '' : (body.caption ?? '').trim()
      media = { mime_type: upload.asset.mime_type, file_name: upload.asset.file_name, size: upload.asset.size, download_url: null }
      blob = upload.blob
    } else {
      return response.untyped(validationError({ type: ['Unsupported message type.'] }))
    }

    if (unregisteredNumbers.has(conversation.phone_number.id)) {
      return response.untyped(
        conflict('phone_number_not_registered', `${conversation.phone_number.display_phone_number} is not registered on the WhatsApp Business Platform.`),
      )
    }
    if (conversation.contact.marketing_opt_in_status === 'opted_out') {
      return response.untyped(conflict('contact_opted_out', 'This contact has opted out of messages.'))
    }
    if (type !== 'template' && !windowOpen(conversation)) {
      return response.untyped(conflict('outside_service_window', 'The customer service window is closed. Send an approved template.'))
    }
    if (type === 'template') {
      const rendered = templateBody(body.template_id ?? '')!
      if (rendered.template.status !== 'APPROVED') {
        return response.untyped(conflict('template_not_approved', 'This template is not approved.'))
      }
      if (rendered.template.category === 'MARKETING' && conversation.contact.marketing_opt_in_status !== 'opted_in') {
        return response.untyped(conflict('marketing_opt_in_required', 'Marketing templates need a recorded opt-in.'))
      }
    }

    const id = uuid()
    const message: MockMessage = {
      id,
      conversation_id: conversation.id,
      direction: 'outbound',
      type,
      text,
      status: 'queued',
      source: 'inbox',
      error_code: '',
      error_message: '',
      template,
      media: media ? { ...media, download_url: mediaUrl(id) } : null,
      reply_to_message_id: body.reply_to_message_id ?? null,
      sent_by: userSummary(ctx.user.id),
      wamid: '',
      created_at: nowIso(),
      sent_at: null,
      delivered_at: null,
      read_at: null,
      failed_at: null,
    }
    state.messages.get(conversation.id)?.push(message)
    if (blob) state.messageBlobs.set(id, blob)
    if (idempotencyKey) state.idempotency.set(idempotencyKey, id)
    conversation.updated_at = message.created_at
    state.sends += 1

    mockRealtime.emit('message.created', { conversation_id: conversation.id, message_id: id, direction: 'outbound' }, ctx.workspace.id)
    emitUpdated(ctx.workspace.id, conversation.id)
    simulateDelivery(state, ctx.workspace.id, conversation, message, state.sends)
    return response(201).json(message)
  }),

  http.get('/api/v1/inbox/conversations/{id}/notes/', async ({ request, params, response }) => {
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    await mockDelay(150)
    const state = inboxState()
    const conversation = findConversation(state, ctx.workspace.id, params.id)
    if (!conversation) return response.untyped(notFound())
    return response(200).json(paginate(request, state.notes.get(conversation.id) ?? [], 100))
  }),

  http.post('/api/v1/inbox/conversations/{id}/notes/', async ({ request, params, response }) => {
    const ctx = authorize(request, 'agent')
    if (ctx instanceof Response) return response.untyped(ctx)
    await mockDelay()
    const state = inboxState()
    const conversation = findConversation(state, ctx.workspace.id, params.id)
    if (!conversation) return response.untyped(notFound())
    const body = await request.json()
    const text = (body.body ?? '').trim()
    if (!text) return response.untyped(validationError({ body: ['This field may not be blank.'] }))
    const note = { id: uuid(), body: text, author: userSummary(ctx.user.id)!, created_at: nowIso() }
    state.notes.get(conversation.id)?.push(note)
    return response(201).json(note)
  }),

  http.post('/api/v1/inbox/media/', async ({ request, response }) => {
    const ctx = authorize(request, 'agent')
    if (ctx instanceof Response) return response.untyped(ctx)
    await mockDelay(600)
    const form = await request.formData()
    const file = form.get('file')
    if (!(file instanceof Blob)) return response.untyped(validationError({ file: ['No file was submitted.'] }))
    const fileName = file instanceof File ? file.name : 'upload'
    const check = validateAttachment({ name: fileName, type: file.type, size: file.size })
    if (!check.ok) return response.untyped(validationError({ file: [check.reason] }))
    const asset = { id: uuid(), mime_type: file.type, file_name: fileName, size: file.size, created_at: nowIso() }
    inboxState().uploads.set(asset.id, { asset, blob: file, workspaceId: ctx.workspace.id })
    return response(201).json(asset)
  }),

  http.get('/api/v1/inbox/messages/{id}/media/', async ({ request, params, response }) => {
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    await mockDelay(300)
    const state = inboxState()
    let message: MockMessage | undefined
    for (const conversation of state.conversations) {
      if (conversation.workspace_id !== ctx.workspace.id) continue
      message = state.messages.get(conversation.id)?.find((candidate) => candidate.id === params.id)
      if (message) break
    }
    if (!message?.media?.download_url) return response.untyped(notFound())
    const { mime_type, file_name } = message.media
    const blob =
      state.messageBlobs.get(message.id) ??
      (mime_type.startsWith('image/')
        ? placeholderImage(message.type === 'sticker' ? 'Sticker' : message.text || 'Photo')
        : mime_type.startsWith('audio/')
          ? placeholderAudio()
          : placeholderDocument(file_name))
    return response.untyped(
      new HttpResponse(blob, {
        status: 200,
        headers: { 'Content-Type': blob.type || 'application/octet-stream', 'Content-Disposition': `attachment; filename="${file_name}"` },
      }),
    )
  }),
]
