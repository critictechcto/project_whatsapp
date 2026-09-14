import { HttpResponse } from 'msw'
import type { Schemas } from '../../../api/types'
import { authorize, errorResponse, http, mockDelay, notFound, nowIso, paginate, uuid, validationError } from '../../../mocks/utils'
import type { AreaMockHandlers } from '../registry/types'
import { phoneNumbersFor, whatsappState, type MockAccount, type MockPhoneNumber } from './mockState'

/**
 * WhatsApp onboarding and phone-number handlers. Embedded Signup creates an account that moves
 * subscribing → registering → completed, one step per read, like the backend's Celery chain.
 */

const noContent = () => new HttpResponse(null, { status: 204 })

function toPhoneNumber(number: MockPhoneNumber): Schemas['PhoneNumber'] {
  const { workspace_id: _workspace, ...rest } = number
  return rest
}

function toAccount(account: MockAccount): Schemas['WhatsAppBusinessAccount'] {
  const { workspace_id: _workspace, ...rest } = account
  return {
    ...rest,
    phone_numbers: whatsappState()
      .numbers.filter((number) => number.waba === account.id)
      .map(toPhoneNumber),
  }
}

/** Advances an in-progress setup by one step. */
function advance(account: MockAccount) {
  const now = nowIso()
  if (account.onboarding_status === 'code_exchanged' || account.onboarding_status === 'subscribing') {
    account.onboarding_status = 'registering'
    account.subscribed_at = now
    account.updated_at = now
    return
  }
  if (account.onboarding_status !== 'registering') return
  const numbers = phoneNumbersFor(account.workspace_id)
  const hasDefault = numbers.some((number) => number.is_default && number.registration_status === 'registered')
  for (const number of numbers.filter((candidate) => candidate.waba === account.id)) {
    number.registration_status = 'registered'
    number.meta_status = 'CONNECTED'
    number.code_verification_status = 'VERIFIED'
    number.last_synced_at = now
    number.updated_at = now
    if (!hasDefault) number.is_default = true
  }
  account.onboarding_status = 'completed'
  account.status = 'active'
  account.updated_at = now
}

function accountIn(workspaceId: string, id: string) {
  return whatsappState().accounts.find((account) => account.id === id && account.workspace_id === workspaceId)
}

function numberIn(workspaceId: string, id: string) {
  return phoneNumbersFor(workspaceId).find((number) => number.id === id)
}

function randomDigits(length: number) {
  let digits = ''
  for (let i = 0; i < length; i++) digits += Math.floor(Math.random() * 10)
  return digits
}

export const handlers: AreaMockHandlers = [
  http.get('/api/v1/whatsapp/signup-config/', ({ request, response }) => {
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    return response(200).json({ app_id: '1234567890123456', config_id: '987654321098765', graph_api_version: 'v23.0' })
  }),

  http.get('/api/v1/whatsapp/accounts/', ({ request, query, response }) => {
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    const status = query.get('status')
    const onboarding = query.get('onboarding_status')
    const accounts = whatsappState().accounts.filter((account) => account.workspace_id === ctx.workspace.id)
    accounts.forEach(advance)
    const items = accounts
      .filter((account) => (!status || account.status === status) && (!onboarding || account.onboarding_status === onboarding))
      .map(toAccount)
    return response(200).json(paginate(request, items))
  }),

  http.get('/api/v1/whatsapp/accounts/{id}/', ({ request, params, response }) => {
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    const account = accountIn(ctx.workspace.id, params.id)
    if (!account) return response.untyped(notFound())
    advance(account)
    return response(200).json(toAccount(account))
  }),

  http.delete('/api/v1/whatsapp/accounts/{id}/', async ({ request, params, response }) => {
    await mockDelay()
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const account = accountIn(ctx.workspace.id, params.id)
    if (!account) return response.untyped(notFound())
    const state = whatsappState()
    state.accounts = state.accounts.filter((candidate) => candidate.id !== account.id)
    state.numbers = state.numbers.filter((number) => number.waba !== account.id)
    return response.untyped(noContent())
  }),

  http.post('/api/v1/whatsapp/accounts/{id}/resync/', async ({ request, params, response }) => {
    await mockDelay()
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const account = accountIn(ctx.workspace.id, params.id)
    if (!account) return response.untyped(notFound())
    const now = nowIso()
    account.updated_at = now
    for (const number of phoneNumbersFor(ctx.workspace.id).filter((candidate) => candidate.waba === account.id)) {
      number.last_synced_at = now
    }
    return response(202).json(toAccount(account))
  }),

  http.post('/api/v1/whatsapp/embedded-signup/', async ({ request, response }) => {
    await mockDelay(600)
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const body = (await request.json()) as Partial<Schemas['EmbeddedSignupRequest']>
    const errors: Record<string, string[]> = {}
    if (!body.code) errors.code = ['This field is required.']
    if (!body.waba_id) errors.waba_id = ['This field is required.']
    if (Object.keys(errors).length) return response.untyped(validationError(errors))
    if (body.code === 'invalid-code') {
      return response.untyped(
        errorResponse(400, 'signup_rejected', 'Meta rejected the signup code. Start the signup again.'),
      )
    }

    const state = whatsappState()
    const existing = state.accounts.find((account) => account.waba_id === body.waba_id)
    if (existing && existing.workspace_id !== ctx.workspace.id) {
      return response.untyped(
        errorResponse(409, 'conflict', 'This WhatsApp Business Account is already connected to another workspace.'),
      )
    }
    if (existing) state.accounts = state.accounts.filter((account) => account.id !== existing.id)

    const now = nowIso()
    const account: MockAccount = {
      id: uuid(),
      workspace_id: ctx.workspace.id,
      waba_id: String(body.waba_id),
      business_id: body.business_id ?? '',
      name: ctx.workspace.name,
      currency: 'INR',
      timezone_id: '71',
      message_template_namespace: uuid().replace(/-/g, '_'),
      status: 'pending',
      onboarding_status: 'subscribing',
      last_error: '',
      subscribed_at: null,
      token_expires_at: new Date(Date.now() + 60 * 86_400_000).toISOString(),
      connected_by: ctx.user.id,
      created_at: now,
      updated_at: now,
    }
    const local = `80471${randomDigits(5)}`
    state.accounts.push(account)
    state.numbers = state.numbers.filter((number) => number.waba !== existing?.id)
    state.numbers.push({
      id: uuid(),
      workspace_id: ctx.workspace.id,
      waba: account.id,
      phone_number_id: body.phone_number_id || randomDigits(15),
      display_phone_number: `+91 ${local.slice(0, 5)} ${local.slice(5)}`,
      phone_e164: `+91${local}`,
      verified_name: ctx.workspace.name,
      name_status: 'PENDING_REVIEW',
      quality_rating: 'UNKNOWN',
      messaging_limit_tier: 'TIER_250',
      throughput_level: 'STANDARD',
      platform_type: 'CLOUD_API',
      code_verification_status: 'VERIFIED',
      meta_status: 'PENDING',
      registration_status: 'pending',
      is_coexistence: Boolean(body.coexistence),
      is_default: false,
      last_synced_at: null,
      last_error: '',
      created_at: now,
      updated_at: now,
    })
    return response(201).json(toAccount(account))
  }),

  http.get('/api/v1/whatsapp/phone-numbers/', ({ request, query, response }) => {
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    const isDefault = query.get('is_default')
    const registration = query.get('registration_status')
    const quality = query.get('quality_rating')
    const waba = query.get('waba')
    const search = (query.get('search') ?? '').toLowerCase()
    const items = phoneNumbersFor(ctx.workspace.id)
      .filter(
        (number) =>
          (isDefault === null || String(number.is_default) === isDefault) &&
          (!registration || number.registration_status === registration) &&
          (!quality || number.quality_rating === quality) &&
          (!waba || number.waba === waba) &&
          (!search || `${number.display_phone_number} ${number.phone_e164} ${number.verified_name}`.toLowerCase().includes(search)),
      )
      .map(toPhoneNumber)
    return response(200).json(paginate(request, items))
  }),

  http.get('/api/v1/whatsapp/phone-numbers/{id}/', ({ request, params, response }) => {
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    const number = numberIn(ctx.workspace.id, params.id)
    if (!number) return response.untyped(notFound())
    return response(200).json(toPhoneNumber(number))
  }),

  http.post('/api/v1/whatsapp/phone-numbers/{id}/refresh/', async ({ request, params, response }) => {
    await mockDelay()
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const number = numberIn(ctx.workspace.id, params.id)
    if (!number) return response.untyped(notFound())
    number.last_synced_at = nowIso()
    number.updated_at = number.last_synced_at
    return response(200).json(toPhoneNumber(number))
  }),

  http.post('/api/v1/whatsapp/phone-numbers/{id}/retry-registration/', async ({ request, params, response }) => {
    await mockDelay()
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const number = numberIn(ctx.workspace.id, params.id)
    if (!number) return response.untyped(notFound())
    number.registration_status = 'registered'
    number.last_error = ''
    number.last_synced_at = nowIso()
    return response(202).json(toPhoneNumber(number))
  }),

  http.post('/api/v1/whatsapp/phone-numbers/{id}/set-default/', async ({ request, params, response }) => {
    await mockDelay()
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const number = numberIn(ctx.workspace.id, params.id)
    if (!number) return response.untyped(notFound())
    if (number.registration_status !== 'registered') {
      return response.untyped(
        errorResponse(409, 'phone_number_not_registered', 'Register this number before making it the default.'),
      )
    }
    for (const other of phoneNumbersFor(ctx.workspace.id)) other.is_default = other.id === number.id
    return response(200).json(toPhoneNumber(number))
  }),
]
