/** Mock handlers for `/api/v1/offers/` (docs/contracts/services-and-offers.md, "Offers"). */
import { ids } from '../../../mocks/seed'
import {
  authorize,
  errorResponse,
  http,
  mockDelay,
  notFound,
  nowIso,
  paginate,
  uuid,
  validationError,
  type MockErrorResponse,
  type WorkspaceContext,
} from '../../../mocks/utils'
import { catalogMock } from '../catalog/mockState'
import type { AreaMockHandlers } from '../registry/types'
import { normalisePhone } from './format'
import { offerState, serializeClaim, serializeCode, userSummary, type MockClaim, type MockOfferCode } from './mockState'
import type { OfferCodeWrite, OfferStats, RedeemAtCounterBody, RedeemClaimBody } from './types'

/** Words the shop, consent and opt-out flows already answer. */
const RESERVED_CODES = ['MENU', 'SHOP', 'CART', 'ORDER', 'HI', 'YES', 'NO', 'STOP', 'UNSUBSCRIBE', 'START', 'HELP', 'CANCEL']
const CODE = /^[A-Za-z0-9_-]{2,20}$/
const CLAIM_STATUSES: readonly string[] = ['claimed', 'applied', 'redeemed', 'expired']

/** Kaveri Dental Clinic's plan doesn't include commerce (as in the analytics mocks). */
function gate(request: Request, minRole: 'viewer' | 'agent' | 'admin' = 'viewer'): WorkspaceContext | MockErrorResponse {
  const ctx = authorize(request, minRole)
  if (ctx instanceof Response) return ctx
  if (ctx.workspace.id === ids.kaveriClinic) {
    return errorResponse(409, 'feature_not_available', 'Selling on WhatsApp is not included in your plan.', { feature: 'commerce' })
  }
  return ctx
}

function codesOf(workspaceId: string) {
  return offerState().codes.filter((code) => code.workspaceId === workspaceId)
}

function findCode(workspaceId: string, id: string) {
  return codesOf(workspaceId).find((code) => code.id === id)
}

function validate(ctx: WorkspaceContext, body: Partial<OfferCodeWrite>, current?: MockOfferCode): Record<string, string[]> {
  const errors: Record<string, string[]> = {}
  const merged = { ...current, ...body }
  const code = (merged.code ?? '').trim().toUpperCase()
  if (!CODE.test(code)) errors.code = ['Use 2 to 20 letters, digits, - or _.']
  else if (RESERVED_CODES.includes(code)) errors.code = [`${code} is already a shop or opt-out keyword. Choose another code.`]
  else if (codesOf(ctx.workspace.id).some((other) => other.code === code && other.id !== current?.id)) {
    errors.code = ['You already have an offer with this code.']
  }
  if (!merged.title?.trim()) errors.title = ['This field may not be blank.']
  else if (merged.title.length > 60) errors.title = ['Ensure this field has no more than 60 characters.']
  if (!merged.reply_text?.trim()) errors.reply_text = ['This field may not be blank.']
  else if (merged.reply_text.length > 900) errors.reply_text = ['Ensure this field has no more than 900 characters.']
  const value = merged.discount_value ?? 0
  if (merged.discount_type === 'percent' && (value < 1 || value > 90)) errors.discount_value = ['Enter a percent from 1 to 90.']
  if (merged.discount_type === 'amount' && value < 100) errors.discount_value = ['The discount must be at least ₹1.']
  if (merged.starts_at && merged.ends_at && merged.ends_at < merged.starts_at) errors.ends_at = ['The end must be after the start.']
  if (merged.applies_to === 'items' && merged.discount_type !== 'none') {
    const chosen = merged.product_ids ?? []
    const catalog = catalogMock().products.filter((product) => product.workspace_id === ctx.workspace.id)
    if (chosen.length === 0) errors.product_ids = ['Choose at least one product or service.']
    else if (chosen.some((id) => !catalog.some((product) => product.id === id))) errors.product_ids = ['Some of these items are not in your catalog.']
  }
  return errors
}

function applyBody(code: MockOfferCode, body: Partial<OfferCodeWrite>) {
  Object.assign(code, body)
  if (body.code !== undefined) code.code = body.code.trim().toUpperCase()
  if (code.discount_type === 'none') code.discount_value = 0
  if (code.discount_type !== 'percent') code.max_discount_paise = null
  if (code.applies_to !== 'items') code.product_ids = []
  code.updated_at = nowIso()
}

/** Whether the code can be used right now (active, within dates, under `max_uses`). */
function available(code: MockOfferCode): boolean {
  const now = Date.now()
  if (!code.is_active) return false
  if (code.starts_at && new Date(code.starts_at).getTime() > now) return false
  if (code.ends_at && new Date(code.ends_at).getTime() < now) return false
  if (code.max_uses !== null) {
    const used = offerState().claims.filter((claim) => claim.offer === code.id && (claim.status === 'applied' || claim.status === 'redeemed')).length
    if (used >= code.max_uses) return false
  }
  return true
}

function discountFor(code: MockOfferCode, billPaise: number | null | undefined): number {
  if (!billPaise) return 0
  if (code.discount_type === 'percent') {
    const discount = Math.floor((billPaise * code.discount_value) / 100)
    return code.max_discount_paise ? Math.min(discount, code.max_discount_paise) : discount
  }
  if (code.discount_type === 'amount') return Math.max(0, Math.min(code.discount_value, billPaise - 100))
  return 0
}

function redeem(claim: MockClaim, code: MockOfferCode, billPaise: number | null | undefined, userId: string) {
  claim.status = 'redeemed'
  claim.redeemed_at = nowIso()
  claim.redeemed_by = userSummary(userId)
  if (billPaise !== undefined && billPaise !== null) {
    claim.bill_paise = billPaise
    if (!claim.order_id) claim.discount_paise = discountFor(code, billPaise)
  }
}

function invalidBill(bill: unknown) {
  return bill !== undefined && bill !== null && (typeof bill !== 'number' || !Number.isInteger(bill) || bill < 0)
}

async function readJson<T>(request: Request): Promise<T> {
  return ((await request.json().catch(() => ({}))) ?? {}) as T
}

function stats(code: MockOfferCode): OfferStats {
  const claims = offerState().claims.filter((claim) => claim.offer === code.id)
  const redeemed = claims.filter((claim) => claim.status === 'redeemed')
  const day = (iso: string) => iso.slice(0, 10)
  const daily = Array.from({ length: 14 }, (_, i) => {
    const date = day(new Date(Date.now() - (13 - i) * 86_400_000).toISOString())
    return {
      date,
      claims: claims.filter((claim) => day(claim.created_at) === date).length,
      redeemed: redeemed.filter((claim) => claim.redeemed_at && day(claim.redeemed_at) === date).length,
    }
  })
  return {
    claims: claims.length,
    from_ads: claims.filter((claim) => claim.ad_source_id || claim.ctwa_clid).length,
    applied: claims.filter((claim) => claim.status === 'applied').length,
    redeemed: redeemed.length,
    // As on the backend: the discount given on redeemed claims.
    discount_paise: redeemed.reduce((sum, claim) => sum + claim.discount_paise, 0),
    revenue_paise: redeemed.reduce((sum, claim) => sum + (claim.bill_paise ?? 0), 0),
    daily,
  }
}

export const handlers: AreaMockHandlers = [
  http.get('/api/v1/offers/codes/', async ({ request, response }) => {
    await mockDelay()
    const ctx = gate(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    const list = [...codesOf(ctx.workspace.id)].sort((a, b) => b.created_at.localeCompare(a.created_at)).map(serializeCode)
    return response(200).json(paginate(request, list))
  }),

  http.post('/api/v1/offers/codes/', async ({ request, response }) => {
    await mockDelay()
    const ctx = gate(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const body = await readJson<Partial<OfferCodeWrite>>(request)
    const errors = validate(ctx, body)
    if (Object.keys(errors).length) return response.untyped(validationError(errors))
    const now = nowIso()
    const code: MockOfferCode = {
      workspaceId: ctx.workspace.id,
      id: uuid(),
      code: '',
      title: '',
      reply_text: '',
      discount_type: 'none',
      discount_value: 0,
      max_discount_paise: null,
      min_order_paise: 0,
      applies_to: 'all',
      product_ids: [],
      starts_at: null,
      ends_at: null,
      max_uses: null,
      max_uses_per_contact: 1,
      is_active: true,
      created_at: now,
      updated_at: now,
    }
    applyBody(code, body)
    offerState().codes.push(code)
    return response(201).json(serializeCode(code))
  }),

  http.get('/api/v1/offers/codes/{id}/', async ({ request, params, response }) => {
    await mockDelay()
    const ctx = gate(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    const code = findCode(ctx.workspace.id, params.id)
    return code ? response(200).json(serializeCode(code)) : response.untyped(notFound())
  }),

  http.patch('/api/v1/offers/codes/{id}/', async ({ request, params, response }) => {
    await mockDelay()
    const ctx = gate(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const code = findCode(ctx.workspace.id, params.id)
    if (!code) return response.untyped(notFound())
    const body = await readJson<Partial<OfferCodeWrite>>(request)
    const errors = validate(ctx, body, code)
    if (Object.keys(errors).length) return response.untyped(validationError(errors))
    applyBody(code, body)
    return response(200).json(serializeCode(code))
  }),

  http.delete('/api/v1/offers/codes/{id}/', async ({ request, params, response }) => {
    await mockDelay()
    const ctx = gate(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const state = offerState()
    const code = findCode(ctx.workspace.id, params.id)
    if (!code) return response.untyped(notFound())
    if (state.claims.some((claim) => claim.offer === code.id)) {
      return response.untyped(errorResponse(409, 'offer_in_use', 'This offer has claims. Turn it off instead of deleting it.'))
    }
    state.codes.splice(state.codes.indexOf(code), 1)
    return response(204).empty()
  }),

  http.get('/api/v1/offers/codes/{id}/stats/', async ({ request, params, response }) => {
    await mockDelay()
    const ctx = gate(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    const code = findCode(ctx.workspace.id, params.id)
    return code ? response(200).json(stats(code)) : response.untyped(notFound())
  }),

  http.get('/api/v1/offers/claims/', async ({ request, query, response }) => {
    await mockDelay()
    const ctx = gate(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    const offer = query.get('offer')
    const status = query.get('status')
    const phone = (query.get('phone') ?? '').replace(/[^\d+]/g, '')
    if (status && !CLAIM_STATUSES.includes(status)) return response.untyped(validationError({ status: [`"${status}" is not a valid choice.`] }))
    const list = offerState()
      .claims.filter(
        (claim) =>
          claim.workspaceId === ctx.workspace.id &&
          (!offer || claim.offer === offer) &&
          (!status || claim.status === status) &&
          (!phone || claim.contact.phone_e164.includes(phone)),
      )
      .sort((a, b) => b.created_at.localeCompare(a.created_at))
      .map(serializeClaim)
    return response(200).json(paginate(request, list))
  }),

  http.post('/api/v1/offers/claims/{id}/redeem/', async ({ request, params, response }) => {
    await mockDelay()
    const ctx = gate(request, 'agent')
    if (ctx instanceof Response) return response.untyped(ctx)
    const claim = offerState().claims.find((item) => item.workspaceId === ctx.workspace.id && item.id === params.id)
    if (!claim) return response.untyped(notFound())
    const code = findCode(ctx.workspace.id, claim.offer)
    if (!code) return response.untyped(notFound())
    const body = await readJson<RedeemClaimBody>(request)
    if (invalidBill(body.bill_paise)) return response.untyped(validationError({ bill_paise: ['Enter a valid amount.'] }))
    if (claim.status !== 'claimed' && claim.status !== 'applied') {
      return response.untyped(
        errorResponse(409, 'invalid_transition', claim.status === 'redeemed' ? 'This claim is already redeemed.' : 'This claim has expired.'),
      )
    }
    redeem(claim, code, body.bill_paise, ctx.user.id)
    return response(200).json(serializeClaim(claim))
  }),

  http.post('/api/v1/offers/redeem/', async ({ request, response }) => {
    await mockDelay()
    const ctx = gate(request, 'agent')
    if (ctx instanceof Response) return response.untyped(ctx)
    const body = await readJson<Partial<RedeemAtCounterBody>>(request)
    const errors: Record<string, string[]> = {}
    const typed = (body.code ?? '').trim().toUpperCase()
    const phone = normalisePhone(body.phone ?? '')
    if (!typed) errors.code = ['This field may not be blank.']
    if (!phone) errors.phone = ['Enter a valid phone number.']
    if (invalidBill(body.bill_paise)) errors.bill_paise = ['Enter a valid amount.']
    if (Object.keys(errors).length || !phone) return response.untyped(validationError(errors))
    const code = codesOf(ctx.workspace.id).find((item) => item.code === typed)
    if (!code) return response.untyped(validationError({ code: ['No offer has this code.'] }))

    const state = offerState()
    const mine = state.claims.filter((claim) => claim.offer === code.id && claim.contact.phone_e164 === phone)
    const open = mine.find((claim) => claim.status === 'claimed' || claim.status === 'applied')
    if (open) {
      if (!code.is_active) return response.untyped(errorResponse(409, 'offer_unavailable', `${code.code} is turned off.`))
      redeem(open, code, body.bill_paise, ctx.user.id)
      return response(201).json(serializeClaim(open))
    }
    if (!available(code)) {
      return response.untyped(
        errorResponse(409, 'offer_unavailable', `${code.code} can't be used right now: it is off, outside its dates or fully used.`),
      )
    }
    if (mine.filter((claim) => claim.status === 'redeemed').length >= code.max_uses_per_contact) {
      return response.untyped(errorResponse(409, 'offer_unavailable', `This customer has already used ${code.code}.`))
    }
    const existing = state.claims.find((claim) => claim.contact.phone_e164 === phone)?.contact
    const claim: MockClaim = {
      workspaceId: ctx.workspace.id,
      id: uuid(),
      offer: code.id,
      contact: existing ?? { id: uuid(), name: '', phone_e164: phone, marketing_opt_in_status: 'unknown' },
      conversation_id: null,
      status: 'claimed',
      order_id: null,
      order_number: null,
      discount_paise: 0,
      bill_paise: null,
      ad_source_id: '',
      ad_source_url: '',
      ad_headline: '',
      ctwa_clid: '',
      redeemed_at: null,
      redeemed_by: null,
      created_at: nowIso(),
    }
    redeem(claim, code, body.bill_paise, ctx.user.id)
    state.claims.push(claim)
    return response(201).json(serializeClaim(claim))
  }),
]
