/**
 * Mock handlers for `/api/v1/offers/` (docs/contracts/services-and-offers.md, "Offers").
 * Plain `msw` handlers because the endpoints aren't in `openapi.yml` yet.
 * TODO: switch to generated types after api:types (typed `http` from `mocks/utils`).
 */
import { http, HttpResponse } from 'msw'
import { ids } from '../../../mocks/seed'
import { apiUrl, authorize, errorResponse, mockDelay, notFound, nowIso, paginate, uuid, validationError, type WorkspaceContext } from '../../../mocks/utils'
import type { AreaMockHandlers } from '../registry/types'
import { normalisePhone } from './format'
import { offerState, serializeClaim, serializeCode, type MockClaim, type MockOfferCode } from './mockState'
import type { OfferClaimStatus, OfferCodeWrite, OfferStats, RedeemAtCounterBody, RedeemClaimBody } from './types'

const url = (path: string) => apiUrl(`/api/v1/offers/${path}`)

/** Words the shop, consent and opt-out flows already answer. */
const RESERVED_CODES = ['MENU', 'SHOP', 'CART', 'ORDER', 'HI', 'YES', 'NO', 'STOP', 'UNSUBSCRIBE', 'START', 'HELP', 'CANCEL']
const CODE = /^[A-Za-z0-9_-]{2,20}$/
const CLAIM_STATUSES: readonly string[] = ['claimed', 'applied', 'redeemed', 'expired']

/** Kaveri Dental Clinic's plan doesn't include commerce (as in the analytics mocks). */
function gate(request: Request, minRole: 'viewer' | 'agent' | 'admin' = 'viewer'): WorkspaceContext | Response {
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

function findCode(workspaceId: string, id: string | readonly string[] | undefined) {
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
  return errors
}

function applyBody(code: MockOfferCode, body: Partial<OfferCodeWrite>) {
  Object.assign(code, body)
  if (body.code !== undefined) code.code = body.code.trim().toUpperCase()
  if (code.discount_type === 'none') code.discount_value = 0
  if (code.discount_type !== 'percent') code.max_discount_paise = null
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

function redeem(claim: MockClaim, code: MockOfferCode, billPaise: number | undefined) {
  claim.status = 'redeemed'
  claim.redeemed_at = nowIso()
  if (billPaise !== undefined) {
    claim.bill_paise = billPaise
    if (!claim.order) claim.discount_paise = discountFor(code, billPaise)
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
  const used = claims.filter((claim) => claim.status === 'applied' || claim.status === 'redeemed')
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
    from_ads: claims.filter((claim) => claim.ad_source_id || claim.ad_headline).length,
    applied: claims.filter((claim) => claim.status === 'applied' || (claim.status === 'redeemed' && claim.order)).length,
    redeemed: redeemed.length,
    discount_paise: used.reduce((sum, claim) => sum + claim.discount_paise, 0),
    revenue_paise: redeemed.reduce((sum, claim) => sum + (claim.bill_paise ?? 0), 0),
    daily,
  }
}

export const handlers: AreaMockHandlers = [
  http.get(url('codes/'), async ({ request }) => {
    await mockDelay()
    const ctx = gate(request)
    if (ctx instanceof Response) return ctx
    const list = [...codesOf(ctx.workspace.id)].sort((a, b) => b.created_at.localeCompare(a.created_at)).map(serializeCode)
    return HttpResponse.json(paginate(request, list))
  }),

  http.post(url('codes/'), async ({ request }) => {
    await mockDelay()
    const ctx = gate(request, 'admin')
    if (ctx instanceof Response) return ctx
    const body = await readJson<Partial<OfferCodeWrite>>(request)
    const errors = validate(ctx, body)
    if (Object.keys(errors).length) return validationError(errors)
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
    return HttpResponse.json(serializeCode(code), { status: 201 })
  }),

  http.get(url('codes/:id/'), async ({ request, params }) => {
    await mockDelay()
    const ctx = gate(request)
    if (ctx instanceof Response) return ctx
    const code = findCode(ctx.workspace.id, params.id)
    return code ? HttpResponse.json(serializeCode(code)) : notFound()
  }),

  http.patch(url('codes/:id/'), async ({ request, params }) => {
    await mockDelay()
    const ctx = gate(request, 'admin')
    if (ctx instanceof Response) return ctx
    const code = findCode(ctx.workspace.id, params.id)
    if (!code) return notFound()
    const body = await readJson<Partial<OfferCodeWrite>>(request)
    const errors = validate(ctx, body, code)
    if (Object.keys(errors).length) return validationError(errors)
    applyBody(code, body)
    return HttpResponse.json(serializeCode(code))
  }),

  http.delete(url('codes/:id/'), async ({ request, params }) => {
    await mockDelay()
    const ctx = gate(request, 'admin')
    if (ctx instanceof Response) return ctx
    const state = offerState()
    const code = findCode(ctx.workspace.id, params.id)
    if (!code) return notFound()
    if (state.claims.some((claim) => claim.offer === code.id)) {
      return errorResponse(409, 'offer_in_use', 'This offer has claims. Turn it off instead of deleting it.')
    }
    state.codes.splice(state.codes.indexOf(code), 1)
    return new HttpResponse(null, { status: 204 })
  }),

  http.get(url('codes/:id/stats/'), async ({ request, params }) => {
    await mockDelay()
    const ctx = gate(request)
    if (ctx instanceof Response) return ctx
    const code = findCode(ctx.workspace.id, params.id)
    return code ? HttpResponse.json(stats(code)) : notFound()
  }),

  http.get(url('claims/'), async ({ request }) => {
    await mockDelay()
    const ctx = gate(request)
    if (ctx instanceof Response) return ctx
    const search = new URL(request.url).searchParams
    const offer = search.get('offer')
    const status = search.get('status')
    const phone = (search.get('phone') ?? '').replace(/[^\d+]/g, '')
    if (status && !CLAIM_STATUSES.includes(status)) return validationError({ status: [`"${status}" is not a valid choice.`] })
    const list = offerState()
      .claims.filter(
        (claim) =>
          claim.workspaceId === ctx.workspace.id &&
          (!offer || claim.offer === offer) &&
          (!status || claim.status === (status as OfferClaimStatus)) &&
          (!phone || claim.contact.phone_e164.includes(phone)),
      )
      .sort((a, b) => b.created_at.localeCompare(a.created_at))
      .map(serializeClaim)
    return HttpResponse.json(paginate(request, list))
  }),

  http.post(url('claims/:id/redeem/'), async ({ request, params }) => {
    await mockDelay()
    const ctx = gate(request, 'agent')
    if (ctx instanceof Response) return ctx
    const claim = offerState().claims.find((item) => item.workspaceId === ctx.workspace.id && item.id === params.id)
    if (!claim) return notFound()
    const code = findCode(ctx.workspace.id, claim.offer)
    if (!code) return notFound()
    const body = await readJson<RedeemClaimBody>(request)
    if (invalidBill(body.bill_paise)) return validationError({ bill_paise: ['Enter a valid amount.'] })
    if (claim.status !== 'claimed' && claim.status !== 'applied') {
      return errorResponse(409, 'invalid_transition', claim.status === 'redeemed' ? 'This claim is already redeemed.' : 'This claim has expired.')
    }
    redeem(claim, code, body.bill_paise)
    return HttpResponse.json(serializeClaim(claim))
  }),

  http.post(url('redeem/'), async ({ request }) => {
    await mockDelay()
    const ctx = gate(request, 'agent')
    if (ctx instanceof Response) return ctx
    const body = await readJson<Partial<RedeemAtCounterBody>>(request)
    const errors: Record<string, string[]> = {}
    const typed = (body.code ?? '').trim().toUpperCase()
    const phone = normalisePhone(body.phone ?? '')
    if (!typed) errors.code = ['This field may not be blank.']
    if (!phone) errors.phone = ['Enter a valid phone number.']
    if (invalidBill(body.bill_paise)) errors.bill_paise = ['Enter a valid amount.']
    if (Object.keys(errors).length) return validationError(errors)
    const code = codesOf(ctx.workspace.id).find((item) => item.code === typed)
    if (!code) return validationError({ code: ['No offer has this code.'] })

    const state = offerState()
    const mine = state.claims.filter((claim) => claim.offer === code.id && claim.contact.phone_e164 === phone)
    const open = mine.find((claim) => claim.status === 'claimed' || claim.status === 'applied')
    if (open) {
      if (!code.is_active) return errorResponse(409, 'offer_unavailable', `${code.code} is turned off.`)
      redeem(open, code, body.bill_paise ?? undefined)
      return HttpResponse.json(serializeClaim(open))
    }
    if (!available(code)) return errorResponse(409, 'offer_unavailable', `${code.code} can't be used right now: it is off, outside its dates or fully used.`)
    if (mine.filter((claim) => claim.status === 'redeemed').length >= code.max_uses_per_contact) {
      return errorResponse(409, 'offer_unavailable', `This customer has already used ${code.code}.`)
    }
    const existing = state.claims.find((claim) => claim.contact.phone_e164 === phone)?.contact
    const claim: MockClaim = {
      workspaceId: ctx.workspace.id,
      id: uuid(),
      offer: code.id,
      contact: existing ?? { id: uuid(), name: '', phone_e164: phone! },
      status: 'claimed',
      order: null,
      discount_paise: 0,
      bill_paise: null,
      ad_source_id: '',
      ad_source_url: '',
      ad_headline: '',
      ctwa_clid: '',
      redeemed_at: null,
      created_at: nowIso(),
    }
    redeem(claim, code, body.bill_paise ?? undefined)
    state.claims.push(claim)
    return HttpResponse.json(serializeClaim(claim), { status: 201 })
  }),
]
