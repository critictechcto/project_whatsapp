import type { Schemas } from '../../../api/types'
import { db } from '../../../mocks/db'
import { authorize, errorResponse, http, mockDelay, notFound, nowIso, paginate, uuid, validationError } from '../../../mocks/utils'
import type { AreaMockHandlers } from '../registry/types'
import { MAX_IMPORT_BYTES, mapColumns, parseCsv } from './lib/csv'
import { isValidE164, normalizePhoneInput } from './lib/phone'
import { contactsMock, type MockConsentEvent, type MockContact, type MockImport, type MockTag } from './mockState'

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const HEX_RE = /^#[0-9a-fA-F]{6}$/
const MAX_IMPORT_ERRORS = 100

const byNewest = <T extends { created_at: string }>(items: T[]) =>
  [...items].sort((a, b) => b.created_at.localeCompare(a.created_at))

function toContact({ workspace_id: _ws, ...contact }: MockContact): Schemas['Contact'] {
  return { ...contact, tags: [...contact.tags], attributes: { ...contact.attributes } }
}

function toTag({ workspace_id: _ws, ...tag }: MockTag): Schemas['Tag'] {
  return tag
}

function toEvent({ workspace_id: _ws, contact_id: _c, ...event }: MockConsentEvent): Schemas['ConsentEvent'] {
  return event
}

function toImport(job: MockImport): Schemas['ContactImport'] {
  const { workspace_id: _ws, polls: _p, rows: _r, header: _h, ...rest } = job
  return { ...rest, errors: [...job.errors], tags: [...job.tags] }
}

function conflict(message: string) {
  return errorResponse(409, 'conflict', message)
}

function phoneError(raw: string): string | null {
  if (!raw.trim()) return 'Phone number is required.'
  return isValidE164(normalizePhoneInput(raw)) ? null : `'${raw}' is not a valid phone number.`
}

function contactFor(workspaceId: string, id: string) {
  return contactsMock().contacts.find((contact) => contact.workspace_id === workspaceId && contact.id === id)
}

function unknownTagIds(workspaceId: string, tagIds: readonly string[]) {
  const known = new Set(contactsMock().tags.filter((tag) => tag.workspace_id === workspaceId).map((tag) => tag.id))
  return tagIds.filter((id) => !known.has(id))
}

type ContactBody = Partial<Schemas['ContactRequest']>

/** Validates a create/PATCH body like `ContactSerializer`. Returns an error response or the cleaned fields. */
function validateContact(workspaceId: string, body: ContactBody, existing?: MockContact) {
  const errors: Record<string, string[]> = {}
  let phone = existing?.phone_e164
  if (body.phone_e164 !== undefined || !existing) {
    const raw = String(body.phone_e164 ?? '')
    const message = phoneError(raw)
    if (message) errors.phone_e164 = [message]
    else phone = normalizePhoneInput(raw)
  }
  if (body.email && !EMAIL_RE.test(body.email)) errors.email = ['Enter a valid email address.']
  if (body.name && body.name.length > 255) errors.name = ['Ensure this field has no more than 255 characters.']
  if (body.attributes !== undefined && (typeof body.attributes !== 'object' || body.attributes === null || Array.isArray(body.attributes))) {
    errors.attributes = ['Expected a dictionary of items.']
  }
  if (body.tags) {
    const missing = unknownTagIds(workspaceId, body.tags)
    if (missing.length) errors.tags = [`Invalid pk "${missing[0]}" - object does not exist.`]
  }
  if (Object.keys(errors).length) return { error: validationError(errors) }

  const clash = contactsMock().contacts.find(
    (contact) => contact.workspace_id === workspaceId && contact.phone_e164 === phone && contact.id !== existing?.id,
  )
  if (clash) return { error: conflict('A contact with this phone number already exists.') }
  return { phone: phone as string }
}

function recordConsent(contact: MockContact, action: 'opt_in' | 'opt_out', source: Schemas['ConsentSourceEnum'], actor: string | null, evidence: string, at = nowIso()) {
  const target = action === 'opt_in' ? 'opted_in' : 'opted_out'
  if (contact.marketing_opt_in_status === target) return
  contact.marketing_opt_in_status = target
  if (action === 'opt_in') {
    contact.opted_in_at = at
    contact.opt_in_source = source
  } else contact.opted_out_at = at
  contact.updated_at = at
  contactsMock().consentEvents.push({
    id: uuid(),
    workspace_id: contact.workspace_id,
    contact_id: contact.id,
    purpose: 'marketing',
    action,
    source,
    evidence,
    actor,
    wamid: '',
    occurred_at: at,
    created_at: at,
  })
}

function addImportError(job: MockImport, row: number | null, error: string) {
  if (job.errors.length < MAX_IMPORT_ERRORS) job.errors.push({ row, error })
}

/** Applies the parsed rows like `apps/contacts/tasks.py` and marks the job completed. */
function completeImport(job: MockImport) {
  const state = contactsMock()
  const columns = mapColumns(job.header)
  const index = (target: string) => columns.find((column) => column.target === target)?.index
  const phoneIndex = index('phone')
  const nameIndex = index('name')
  const emailIndex = index('email')
  const now = nowIso()
  const cell = (cells: string[], i: number | undefined) => (i !== undefined && i < cells.length ? cells[i].trim() : '')
  const seen = new Set<string>()
  const opt = job.mark_opted_in && job.consent_attested

  job.total_rows = job.rows.length
  for (const { line, cells } of job.rows) {
    const rawPhone = cell(cells, phoneIndex)
    const message = phoneError(rawPhone)
    if (message) {
      job.error_count += 1
      addImportError(job, line, message)
      continue
    }
    const email = cell(cells, emailIndex)
    if (email && !EMAIL_RE.test(email)) {
      job.error_count += 1
      addImportError(job, line, `'${email}' is not a valid email address.`)
      continue
    }
    const phone = normalizePhoneInput(rawPhone)
    const attributes: Record<string, string> = {}
    for (const column of columns) {
      if (column.target === 'attribute' && cell(cells, column.index)) attributes[column.key] = cell(cells, column.index)
    }
    let contact = state.contacts.find((c) => c.workspace_id === job.workspace_id && c.phone_e164 === phone)
    if (!contact) {
      contact = {
        id: uuid(),
        workspace_id: job.workspace_id,
        phone_e164: phone,
        wa_id: phone.slice(1),
        name: cell(cells, nameIndex),
        email,
        attributes,
        tags: [],
        marketing_opt_in_status: 'unknown',
        opted_in_at: null,
        opted_out_at: null,
        opt_in_source: '',
        last_inbound_at: null,
        created_at: now,
        updated_at: now,
      }
      state.contacts.push(contact)
      job.created_count += 1
    } else {
      contact.name = cell(cells, nameIndex) || contact.name
      contact.email = email || contact.email
      contact.attributes = { ...contact.attributes, ...attributes }
      contact.updated_at = now
      if (!seen.has(phone)) job.updated_count += 1
    }
    for (const tagId of job.tags) if (!contact.tags.includes(tagId)) contact.tags.push(tagId)
    if (opt && !seen.has(phone)) {
      if (contact.marketing_opt_in_status === 'unknown') {
        recordConsent(
          contact,
          'opt_in',
          'import',
          job.created_by,
          `Contact import ${job.id}; consent attested by the uploader. Opt-in source: ${job.opt_in_source}`,
          now,
        )
      } else if (contact.marketing_opt_in_status === 'opted_out') {
        job.skipped_count += 1
        addImportError(job, line, 'Contact has opted out of marketing; imported without opting in.')
      }
    }
    seen.add(phone)
  }
  job.status = 'completed'
  job.finished_at = now
}

/** One step per poll: queued → processing (half) → processing (all rows) → completed. */
function advanceImport(job: MockImport) {
  if (job.status === 'completed' || job.status === 'failed') return
  job.polls += 1
  if (job.polls === 1) {
    job.status = 'processing'
    job.started_at = nowIso()
    if (!mapColumns(job.header).some((column) => column.target === 'phone')) {
      job.status = 'failed'
      job.finished_at = nowIso()
      addImportError(job, null, 'No phone column found. Name one column phone, phone_number, mobile, whatsapp, number.')
      return
    }
    job.total_rows = Math.ceil(job.rows.length / 2)
  } else if (job.polls === 2) {
    job.total_rows = job.rows.length
  } else {
    completeImport(job)
  }
}

export const handlers: AreaMockHandlers = [
  // Member names for the consent timeline. The shared handler is registered after
  // `GET /api/v1/workspaces/{id}/`, which reads "members" as a workspace id and returns 404.
  http.get('/api/v1/workspaces/members/', ({ request, response }) => {
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    const items = db.memberships
      .filter((membership) => membership.workspace_id === ctx.workspace.id)
      .flatMap((membership) => {
        const user = db.users.find((candidate) => candidate.id === membership.user_id)
        return user
          ? [{ id: membership.id, role: membership.role, created_at: membership.created_at, user: { id: user.id, email: user.email, full_name: user.full_name } }]
          : []
      })
    return response(200).json(paginate(request, items))
  }),

  // Contacts
  http.get('/api/v1/contacts/', async ({ request, query, response }) => {
    await mockDelay(200)
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    const search = (query.get('search') ?? '').trim().toLowerCase()
    const digits = search.replace(/\D/g, '')
    const tag = query.get('tag')
    const status = query.get('marketing_opt_in_status')
    const items = contactsMock().contacts.filter(
      (c) =>
        c.workspace_id === ctx.workspace.id &&
        (!tag || c.tags.includes(tag)) &&
        (!status || c.marketing_opt_in_status === status) &&
        (!search ||
          (c.name ?? '').toLowerCase().includes(search) ||
          (c.email ?? '').toLowerCase().includes(search) ||
          c.phone_e164.includes(search) ||
          (digits.length >= 3 && c.phone_e164.includes(digits))),
    )
    return response(200).json(paginate(request, byNewest(items).map(toContact), 25))
  }),

  http.post('/api/v1/contacts/', async ({ request, response }) => {
    await mockDelay()
    const ctx = authorize(request, 'agent')
    if (ctx instanceof Response) return response.untyped(ctx)
    const body = (await request.json()) as ContactBody
    const result = validateContact(ctx.workspace.id, body)
    if ('error' in result) return response.untyped(result.error!)
    const now = nowIso()
    const contact: MockContact = {
      id: uuid(),
      workspace_id: ctx.workspace.id,
      phone_e164: result.phone,
      wa_id: result.phone.slice(1),
      name: body.name ?? '',
      email: body.email ?? '',
      attributes: (body.attributes as Record<string, unknown>) ?? {},
      tags: [...new Set(body.tags ?? [])],
      marketing_opt_in_status: 'unknown',
      opted_in_at: null,
      opted_out_at: null,
      opt_in_source: '',
      last_inbound_at: null,
      created_at: now,
      updated_at: now,
    }
    contactsMock().contacts.push(contact)
    return response(201).json(toContact(contact))
  }),

  http.post('/api/v1/contacts/bulk-tag/', async ({ request, response }) => {
    await mockDelay()
    const ctx = authorize(request, 'agent')
    if (ctx instanceof Response) return response.untyped(ctx)
    const body = (await request.json()) as Partial<Schemas['BulkTagRequest']>
    const contactIds = [...new Set(body.contact_ids ?? [])]
    const add = [...new Set(body.add_tag_ids ?? [])]
    const remove = [...new Set(body.remove_tag_ids ?? [])]
    if (!contactIds.length) return response.untyped(validationError({ contact_ids: ['This list may not be empty.'] }))
    if (!add.length && !remove.length) {
      return response.untyped(validationError({ non_field_errors: ['Pass add_tag_ids and/or remove_tag_ids.'] }))
    }
    if (add.some((id) => remove.includes(id))) {
      return response.untyped(validationError({ non_field_errors: ["A tag can't be both added and removed."] }))
    }
    const contacts = contactIds.map((id) => contactFor(ctx.workspace.id, id))
    const errors: Record<string, string[]> = {}
    const missing = contactIds.filter((_, i) => !contacts[i])
    if (missing.length) errors.contact_ids = [`Unknown contact ids: ${JSON.stringify(missing)}`]
    if (unknownTagIds(ctx.workspace.id, add).length) errors.add_tag_ids = ['Unknown tag ids.']
    if (unknownTagIds(ctx.workspace.id, remove).length) errors.remove_tag_ids = ['Unknown tag ids.']
    if (Object.keys(errors).length) return response.untyped(validationError(errors))

    let added = 0
    let removed = 0
    const now = nowIso()
    for (const contact of contacts as MockContact[]) {
      const before = contact.tags.length
      contact.tags = contact.tags.filter((id) => !remove.includes(id))
      removed += before - contact.tags.length
      for (const id of add) {
        if (!contact.tags.includes(id)) {
          contact.tags.push(id)
          added += 1
        }
      }
      contact.updated_at = now
    }
    return response(200).json({ contact_count: contacts.length, added, removed })
  }),

  // Tags
  http.get('/api/v1/contacts/tags/', ({ request, query, response }) => {
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    const search = (query.get('search') ?? '').toLowerCase()
    const items = contactsMock().tags.filter(
      (tag) => tag.workspace_id === ctx.workspace.id && (!search || tag.name.toLowerCase().includes(search)),
    )
    return response(200).json(paginate(request, byNewest(items).map(toTag), 100))
  }),

  http.post('/api/v1/contacts/tags/', async ({ request, response }) => {
    await mockDelay()
    const ctx = authorize(request, 'agent')
    if (ctx instanceof Response) return response.untyped(ctx)
    const body = (await request.json()) as Partial<Schemas['TagRequest']>
    const name = String(body.name ?? '').trim()
    const color = body.color ?? ''
    if (!name) return response.untyped(validationError({ name: ['This field may not be blank.'] }))
    if (name.length > 64) return response.untyped(validationError({ name: ['Ensure this field has no more than 64 characters.'] }))
    if (color && !HEX_RE.test(color)) return response.untyped(validationError({ color: ['Use a hex color such as #25D366.'] }))
    const state = contactsMock()
    if (state.tags.some((tag) => tag.workspace_id === ctx.workspace.id && tag.name.toLowerCase() === name.toLowerCase())) {
      return response.untyped(conflict('A tag with this name already exists.'))
    }
    const tag: MockTag = { id: uuid(), name, color, created_at: nowIso(), workspace_id: ctx.workspace.id }
    state.tags.push(tag)
    return response(201).json(toTag(tag))
  }),

  http.get('/api/v1/contacts/tags/{id}/', ({ request, params, response }) => {
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    const tag = contactsMock().tags.find((t) => t.workspace_id === ctx.workspace.id && t.id === params.id)
    return tag ? response(200).json(toTag(tag)) : response.untyped(notFound())
  }),

  http.patch('/api/v1/contacts/tags/{id}/', async ({ request, params, response }) => {
    await mockDelay()
    const ctx = authorize(request, 'agent')
    if (ctx instanceof Response) return response.untyped(ctx)
    const state = contactsMock()
    const tag = state.tags.find((t) => t.workspace_id === ctx.workspace.id && t.id === params.id)
    if (!tag) return response.untyped(notFound())
    const body = (await request.json()) as Schemas['PatchedTagRequest']
    if (body.name !== undefined) {
      const name = body.name.trim()
      if (!name) return response.untyped(validationError({ name: ['This field may not be blank.'] }))
      if (state.tags.some((t) => t.workspace_id === ctx.workspace.id && t.id !== tag.id && t.name.toLowerCase() === name.toLowerCase())) {
        return response.untyped(conflict('A tag with this name already exists.'))
      }
      tag.name = name
    }
    if (body.color !== undefined) {
      if (body.color && !HEX_RE.test(body.color)) return response.untyped(validationError({ color: ['Use a hex color such as #25D366.'] }))
      tag.color = body.color
    }
    return response(200).json(toTag(tag))
  }),

  http.delete('/api/v1/contacts/tags/{id}/', ({ request, params, response }) => {
    const ctx = authorize(request, 'agent')
    if (ctx instanceof Response) return response.untyped(ctx)
    const state = contactsMock()
    const tag = state.tags.find((t) => t.workspace_id === ctx.workspace.id && t.id === params.id)
    if (!tag) return response.untyped(notFound())
    state.tags = state.tags.filter((t) => t !== tag)
    for (const contact of state.contacts) contact.tags = contact.tags.filter((id) => id !== tag.id)
    return response(204).empty()
  }),

  // Imports
  http.get('/api/v1/contacts/imports/', ({ request, response }) => {
    const ctx = authorize(request, 'agent')
    if (ctx instanceof Response) return response.untyped(ctx)
    const items = contactsMock().imports.filter((job) => job.workspace_id === ctx.workspace.id)
    return response(200).json(paginate(request, byNewest(items).map(toImport)))
  }),

  http.post('/api/v1/contacts/imports/', async ({ request, response }) => {
    await mockDelay(400)
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    let form: FormData
    try {
      form = await request.formData()
    } catch {
      return response.untyped(validationError({ file: ['The submitted data was not a file. Check the encoding type on the form.'] }))
    }
    const file = form.get('file')
    const flag = (key: string) => form.get(key) === 'true'
    const optInSource = String(form.get('opt_in_source') ?? '').trim()
    const tagIds = form.getAll('tag_ids').map(String)
    const errors: Record<string, string[]> = {}
    if (!file || typeof file === 'string') errors.file = ['No file was submitted.']
    else if (file.size > MAX_IMPORT_BYTES) errors.file = ['The file is larger than the 10 MB limit.']
    else if (!file.name.toLowerCase().endsWith('.csv')) errors.file = ['Upload a .csv file.']
    if (unknownTagIds(ctx.workspace.id, tagIds).length) errors.tag_ids = [`Invalid pk "${unknownTagIds(ctx.workspace.id, tagIds)[0]}" - object does not exist.`]
    if (flag('mark_opted_in')) {
      if (!flag('consent_attested')) errors.consent_attested = ['Confirm these contacts agreed to receive marketing messages.']
      if (!optInSource) errors.opt_in_source = ['Say where these contacts opted in.']
    }
    if (Object.keys(errors).length || !file || typeof file === 'string') return response.untyped(validationError(errors))

    const parsed = parseCsv(await file.text())
    const [header = [], ...rest] = parsed
    const job: MockImport = {
      id: uuid(),
      workspace_id: ctx.workspace.id,
      file_name: file.name,
      status: 'queued',
      total_rows: 0,
      created_count: 0,
      updated_count: 0,
      skipped_count: 0,
      error_count: 0,
      errors: [],
      mark_opted_in: flag('mark_opted_in'),
      consent_attested: flag('consent_attested'),
      opt_in_source: optInSource,
      tags: tagIds,
      created_by: ctx.user.id,
      started_at: null,
      finished_at: null,
      created_at: nowIso(),
      polls: 0,
      header,
      rows: rest.map((cells, i) => ({ line: i + 2, cells })).filter(({ cells }) => cells.some((cell) => cell.trim())),
    }
    contactsMock().imports.push(job)
    return response(201).json(toImport(job))
  }),

  http.get('/api/v1/contacts/imports/{id}/', ({ request, params, response }) => {
    const ctx = authorize(request, 'agent')
    if (ctx instanceof Response) return response.untyped(ctx)
    const job = contactsMock().imports.find((j) => j.workspace_id === ctx.workspace.id && j.id === params.id)
    if (!job) return response.untyped(notFound())
    advanceImport(job)
    return response(200).json(toImport(job))
  }),

  // Contact by id (after tags/imports so those paths are not read as ids)
  http.get('/api/v1/contacts/{id}/', ({ request, params, response }) => {
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    const contact = contactFor(ctx.workspace.id, params.id)
    return contact ? response(200).json(toContact(contact)) : response.untyped(notFound())
  }),

  http.patch('/api/v1/contacts/{id}/', async ({ request, params, response }) => {
    await mockDelay()
    const ctx = authorize(request, 'agent')
    if (ctx instanceof Response) return response.untyped(ctx)
    const contact = contactFor(ctx.workspace.id, params.id)
    if (!contact) return response.untyped(notFound())
    const body = (await request.json()) as ContactBody
    const result = validateContact(ctx.workspace.id, body, contact)
    if ('error' in result) return response.untyped(result.error!)
    contact.phone_e164 = result.phone
    contact.wa_id = result.phone.slice(1)
    if (body.name !== undefined) contact.name = body.name
    if (body.email !== undefined) contact.email = body.email
    if (body.attributes !== undefined) contact.attributes = body.attributes as Record<string, unknown>
    if (body.tags !== undefined) contact.tags = [...new Set(body.tags)]
    contact.updated_at = nowIso()
    return response(200).json(toContact(contact))
  }),

  http.delete('/api/v1/contacts/{id}/', ({ request, params, response }) => {
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const state = contactsMock()
    const contact = contactFor(ctx.workspace.id, params.id)
    if (!contact) return response.untyped(notFound())
    state.contacts = state.contacts.filter((c) => c !== contact)
    state.consentEvents = state.consentEvents.filter((event) => event.contact_id !== contact.id)
    state.conversations = state.conversations.filter((conversation) => conversation.contact.id !== contact.id)
    return response(204).empty()
  }),

  http.get('/api/v1/contacts/{id}/consent-events/', ({ request, params, response }) => {
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    if (!contactFor(ctx.workspace.id, params.id)) return response.untyped(notFound())
    const events = contactsMock().consentEvents.filter((event) => event.contact_id === params.id)
    return response(200).json(paginate(request, byNewest(events).map(toEvent)))
  }),

  http.post('/api/v1/contacts/{id}/opt-in/', async ({ request, params, response }) => {
    await mockDelay()
    const ctx = authorize(request, 'agent')
    if (ctx instanceof Response) return response.untyped(ctx)
    const contact = contactFor(ctx.workspace.id, params.id)
    if (!contact) return response.untyped(notFound())
    const body = (await request.json()) as Partial<Schemas['OptInRequestRequest']>
    const evidence = (body.evidence ?? '').trim()
    if (body.source && body.source !== 'manual' && body.source !== 'api') {
      return response.untyped(validationError({ source: [`"${body.source}" is not a valid choice.`] }))
    }
    if (!evidence) return response.untyped(validationError({ evidence: ['Describe how the customer opted in.'] }))
    recordConsent(contact, 'opt_in', body.source ?? 'manual', ctx.user.id, evidence)
    return response(200).json(toContact(contact))
  }),

  http.post('/api/v1/contacts/{id}/opt-out/', async ({ request, params, response }) => {
    await mockDelay()
    const ctx = authorize(request, 'agent')
    if (ctx instanceof Response) return response.untyped(ctx)
    const contact = contactFor(ctx.workspace.id, params.id)
    if (!contact) return response.untyped(notFound())
    const body = (await request.json()) as Partial<Schemas['ConsentRequestRequest']>
    recordConsent(contact, 'opt_out', body.source ?? 'manual', ctx.user.id, (body.evidence ?? '').trim())
    return response(200).json(toContact(contact))
  }),

  // Inbox lookups used by "Open conversation" (the inbox area's handlers take precedence once merged).
  http.get('/api/v1/inbox/conversations/', ({ request, query, response }) => {
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    const search = (query.get('search') ?? '').toLowerCase()
    const items = contactsMock().conversations.filter(
      (c) =>
        c.workspace_id === ctx.workspace.id &&
        (!search || c.contact.name.toLowerCase().includes(search) || c.contact.phone_e164.includes(search)),
    )
    return response(200).json(paginate(request, items.map(({ workspace_id: _w, ...conversation }) => conversation)))
  }),

  http.post('/api/v1/inbox/conversations/', async ({ request, response }) => {
    await mockDelay()
    const ctx = authorize(request, 'agent')
    if (ctx instanceof Response) return response.untyped(ctx)
    const body = (await request.json()) as Partial<Schemas['StartConversationRequest']>
    const contact = body.contact_id ? contactFor(ctx.workspace.id, body.contact_id) : undefined
    if (!contact) return response.untyped(validationError({ contact_id: ['Contact not found.'] }))
    const state = contactsMock()
    const existing = state.conversations.find((c) => c.workspace_id === ctx.workspace.id && c.contact.id === contact.id)
    const toConversation = ({ workspace_id: _w, ...conversation }: (typeof state.conversations)[number]) => conversation
    if (existing) return response(200).json(toConversation(existing))
    const now = nowIso()
    const conversation = {
      id: uuid(),
      workspace_id: ctx.workspace.id,
      contact: { id: contact.id, name: contact.name ?? '', phone_e164: contact.phone_e164, marketing_opt_in_status: contact.marketing_opt_in_status },
      phone_number: { id: '7e3a9b1c-5d2f-4a8e-b6c0-9f1e3d5a7b22', display_phone_number: '+91 98290 11223', verified_name: 'Sharma Sweets' },
      status: 'open' as const,
      assignee: null,
      unread_count: 0,
      last_message_at: null,
      last_inbound_at: contact.last_inbound_at,
      service_window_expires_at: null,
      window_open: false,
      last_message: null,
      created_at: now,
      updated_at: now,
    }
    state.conversations.push(conversation)
    return response(201).json(toConversation(conversation))
  }),
]
