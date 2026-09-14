import type { Schemas } from '../../../api/types'
import { ANNUAL_MONTHS_CHARGED, plans as sitePlans, site } from '../../../config/site'
import { db } from '../../../mocks/db'
import { daysAgo, ids } from '../../../mocks/seed'
import { authorize, errorResponse, http, mockDelay, nowIso, paginate, uuid, validationError } from '../../../mocks/utils'
import type { AreaMockHandlers } from '../registry/types'
import { phoneNumbersFor } from '../whatsapp/mockState'
import { GST_STATES, GSTIN_PATTERN } from './gst'

/**
 * Billing handlers. Checkout returns a Razorpay-style session; verify marks the subscription
 * `pending` and it turns `active` a few seconds later (like the Razorpay webhook), adding a GST invoice.
 */

type Plan = Schemas['Plan']
type Subscription = Schemas['Subscription']
type Profile = Schemas['BillingProfile']
type Invoice = Schemas['Invoice']
type Interval = Schemas['BillingIntervalEnum']

/** Mock supplier state (Karnataka): same-state customers get CGST + SGST, others IGST. */
const SUPPLIER_STATE = '29'
const ACTIVATION_DELAY_MS = 6000

const planLimits: Record<string, Plan['limits']> = {
  starter: { whatsapp_numbers: 1, members: 2, contacts: 5000 },
  growth: { whatsapp_numbers: 2, members: 5, contacts: 25000 },
  pro: { whatsapp_numbers: 5, members: 15, contacts: 100000 },
}

const apiPlans: Plan[] = sitePlans.map((plan) => ({
  id: plan.id,
  name: plan.name,
  monthly_price_paise: plan.monthlyPrice * 100,
  annual_price_paise: plan.monthlyPrice * 100 * ANNUAL_MONTHS_CHARGED,
  limits: planLimits[plan.id] ?? { whatsapp_numbers: null, members: null, contacts: null },
  features: plan.features,
}))

const planById = (id: string) => apiPlans.find((plan) => plan.id === id)

type BillingRecord = {
  subscription: Subscription
  profile: Profile
  invoices: Invoice[]
  checkout: { subscriptionId: string; plan: Plan; interval: Interval } | null
  activateAt: number | null
}

const emptyProfile: Profile = {
  legal_name: '',
  gstin: '',
  email: '',
  address_line1: '',
  address_line2: '',
  city: '',
  state_code: '',
  postal_code: '',
}

function trial(endsAt: string): Subscription {
  return {
    plan: planById('growth')!,
    status: 'trialing',
    interval: 'monthly',
    trial_ends_at: endsAt,
    current_period_start: null,
    current_period_end: null,
    cancel_at_period_end: false,
  }
}

function addPeriod(start: Date, interval: Interval): Date {
  const end = new Date(start)
  if (interval === 'annual') end.setFullYear(end.getFullYear() + 1)
  else end.setMonth(end.getMonth() + 1)
  return end
}

function taxes(subtotal: number, stateCode: string) {
  if (stateCode === SUPPLIER_STATE) {
    const half = Math.round((subtotal * site.gstRate) / 200)
    return { cgst_paise: half, sgst_paise: half, igst_paise: 0, total_paise: subtotal + half * 2 }
  }
  const igst = Math.round((subtotal * site.gstRate) / 100)
  return { cgst_paise: 0, sgst_paise: 0, igst_paise: igst, total_paise: subtotal + igst }
}

let invoiceSequence = 142

function makeInvoice(number: number, subtotal: number, stateCode: string, issuedAt: string, periodEnd: string): Invoice {
  return {
    id: uuid(),
    number: `UPC/2026-27/${String(number).padStart(6, '0')}`,
    status: 'paid',
    issued_at: issuedAt,
    period_start: issuedAt,
    period_end: periodEnd,
    subtotal_paise: subtotal,
    ...taxes(subtotal, stateCode),
    download_url: null,
  }
}

function build(): Map<string, BillingRecord> {
  invoiceSequence = 142
  const records = new Map<string, BillingRecord>()
  records.set(ids.sharmaSweets, {
    subscription: trial(new Date(Date.now() + 9 * 86_400_000).toISOString()),
    profile: { ...emptyProfile },
    invoices: [],
    checkout: null,
    activateAt: null,
  })
  const starter = planById('starter')!
  records.set(ids.kaveriClinic, {
    subscription: {
      plan: starter,
      status: 'active',
      interval: 'annual',
      trial_ends_at: null,
      current_period_start: daysAgo(40),
      current_period_end: daysAgo(-325),
      cancel_at_period_end: false,
    },
    profile: {
      legal_name: 'Kaveri Dental Clinic LLP',
      gstin: '29AAKFK4821M1Z3',
      email: 'accounts@kaveridental.in',
      address_line1: '14, 2nd Cross, 80 Feet Road',
      address_line2: 'Indiranagar',
      city: 'Bengaluru',
      state_code: '29',
      postal_code: '560038',
    },
    invoices: [
      makeInvoice(142, starter.annual_price_paise, '29', daysAgo(40), daysAgo(-325)),
      makeInvoice(87, starter.monthly_price_paise, '29', daysAgo(71), daysAgo(41)),
    ],
    checkout: null,
    activateAt: null,
  })
  return records
}

let snapshot: unknown = null
let records = build()

function recordFor(workspaceId: string): BillingRecord {
  if (snapshot !== db.users) {
    snapshot = db.users
    records = build()
  }
  let record = records.get(workspaceId)
  if (!record) {
    const workspace = db.workspaces.find((candidate) => candidate.id === workspaceId)
    const created = workspace ? new Date(workspace.created_at).getTime() : Date.now()
    record = {
      subscription: trial(new Date(created + site.trialDays * 86_400_000).toISOString()),
      profile: { ...emptyProfile },
      invoices: [],
      checkout: null,
      activateAt: null,
    }
    records.set(workspaceId, record)
  }
  return record
}

/** Simulates the Razorpay `subscription.charged` webhook arriving after verify. */
function settle(record: BillingRecord) {
  if (record.subscription.status !== 'pending' || record.activateAt === null || Date.now() < record.activateAt || !record.checkout) return
  const { plan, interval } = record.checkout
  const start = new Date()
  const end = addPeriod(start, interval)
  record.subscription = {
    plan,
    status: 'active',
    interval,
    trial_ends_at: null,
    current_period_start: start.toISOString(),
    current_period_end: end.toISOString(),
    cancel_at_period_end: false,
  }
  invoiceSequence += 1
  const subtotal = interval === 'annual' ? plan.annual_price_paise : plan.monthly_price_paise
  record.invoices.unshift(makeInvoice(invoiceSequence, subtotal, record.profile.state_code, start.toISOString(), end.toISOString()))
  record.checkout = null
  record.activateAt = null
}

function profileErrors(profile: Profile): Record<string, string[]> {
  const errors: Record<string, string[]> = {}
  const required = ['legal_name', 'email', 'address_line1', 'city', 'state_code', 'postal_code'] as const
  for (const key of required) if (!profile[key].trim()) errors[key] = ['This field may not be blank.']
  if (profile.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(profile.email)) errors.email = ['Enter a valid email address.']
  if (profile.state_code && !GST_STATES.some((state) => state.code === profile.state_code)) {
    errors.state_code = [`"${profile.state_code}" is not a valid choice.`]
  }
  if (profile.postal_code && !/^\d{6}$/.test(profile.postal_code)) errors.postal_code = ['Enter a valid 6-digit PIN code.']
  if (profile.gstin && !GSTIN_PATTERN.test(profile.gstin)) {
    errors.gstin = ['Enter a valid GSTIN.']
  } else if (profile.gstin && profile.state_code && profile.gstin.slice(0, 2) !== profile.state_code) {
    errors.state_code = ['Must match the first two digits of the GSTIN.']
  }
  return errors
}

function isComplete(profile: Profile) {
  return Object.keys(profileErrors(profile)).length === 0
}

export const handlers: AreaMockHandlers = [
  http.get('/api/v1/billing/plans/', ({ request, response }) => {
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    return response(200).json(apiPlans)
  }),

  http.get('/api/v1/billing/subscription/', ({ request, response }) => {
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    const record = recordFor(ctx.workspace.id)
    settle(record)
    return response(200).json(record.subscription)
  }),

  http.post('/api/v1/billing/subscription/checkout/', async ({ request, response }) => {
    await mockDelay()
    const ctx = authorize(request, 'owner')
    if (ctx instanceof Response) return response.untyped(ctx)
    const record = recordFor(ctx.workspace.id)
    const body = (await request.json()) as Partial<Schemas['CheckoutRequest']>
    const plan = planById(String(body.plan_id ?? ''))
    const errors: Record<string, string[]> = {}
    if (!plan) errors.plan_id = ['Unknown plan.']
    if (body.interval !== 'monthly' && body.interval !== 'annual') errors.interval = [`"${String(body.interval)}" is not a valid choice.`]
    if (Object.keys(errors).length || !plan || !body.interval) return response.untyped(validationError(errors))
    if (!isComplete(record.profile)) {
      return response.untyped(
        errorResponse(409, 'billing_profile_required', 'Add your billing details before subscribing.'),
      )
    }
    const { subscription } = record
    if (subscription.status === 'active' && subscription.plan.id === plan.id && subscription.interval === body.interval) {
      return response.untyped(errorResponse(409, 'conflict', "You're already on this plan."))
    }
    const subscriptionId = `sub_mock${uuid().replace(/-/g, '').slice(0, 14)}`
    record.checkout = { subscriptionId, plan, interval: body.interval }
    return response(200).json({
      key_id: 'rzp_test_mock',
      subscription_id: subscriptionId,
      name: site.name,
      description: `${plan.name} plan, billed ${body.interval}`,
      prefill: { name: ctx.user.full_name ?? '', email: record.profile.email || ctx.user.email },
    })
  }),

  http.post('/api/v1/billing/subscription/verify/', async ({ request, response }) => {
    await mockDelay()
    const ctx = authorize(request, 'owner')
    if (ctx instanceof Response) return response.untyped(ctx)
    const record = recordFor(ctx.workspace.id)
    const body = (await request.json()) as Partial<Schemas['CheckoutVerifyRequest']>
    if (
      !record.checkout ||
      body.razorpay_subscription_id !== record.checkout.subscriptionId ||
      !body.razorpay_payment_id ||
      !body.razorpay_signature
    ) {
      return response.untyped(
        errorResponse(
          400,
          'payment_verification_failed',
          `We couldn't verify this payment. If money was deducted, contact ${site.email.support}.`,
        ),
      )
    }
    record.subscription = { ...record.subscription, plan: record.checkout.plan, interval: record.checkout.interval, status: 'pending' }
    record.activateAt = Date.now() + ACTIVATION_DELAY_MS
    return response(200).json(record.subscription)
  }),

  http.post('/api/v1/billing/subscription/cancel/', async ({ request, response }) => {
    await mockDelay()
    const ctx = authorize(request, 'owner')
    if (ctx instanceof Response) return response.untyped(ctx)
    const record = recordFor(ctx.workspace.id)
    const body = (await request.json().catch(() => ({}))) as Partial<Schemas['CancelSubscriptionRequest']>
    const { subscription } = record
    if (subscription.status !== 'active' && subscription.status !== 'halted') {
      return response.untyped(errorResponse(409, 'conflict', "There's no active subscription to cancel."))
    }
    record.subscription =
      body.at_period_end === false
        ? { ...subscription, status: 'cancelled', cancel_at_period_end: false, current_period_end: nowIso() }
        : { ...subscription, cancel_at_period_end: true }
    return response(200).json(record.subscription)
  }),

  http.get('/api/v1/billing/billing-profile/', ({ request, response }) => {
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    return response(200).json(recordFor(ctx.workspace.id).profile)
  }),

  http.patch('/api/v1/billing/billing-profile/', async ({ request, response }) => {
    await mockDelay()
    const ctx = authorize(request, 'owner')
    if (ctx instanceof Response) return response.untyped(ctx)
    const record = recordFor(ctx.workspace.id)
    const body = (await request.json()) as Schemas['PatchedBillingProfileRequest']
    const next: Profile = { ...record.profile }
    for (const key of Object.keys(emptyProfile) as (keyof Profile)[]) {
      const value = body[key]
      if (typeof value === 'string') next[key] = value.trim()
    }
    next.gstin = next.gstin.replace(/\s+/g, '').toUpperCase()
    const errors = profileErrors(next)
    if (Object.keys(errors).length) return response.untyped(validationError(errors))
    record.profile = next
    return response(200).json(next)
  }),

  http.get('/api/v1/billing/invoices/', ({ request, response }) => {
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const record = recordFor(ctx.workspace.id)
    settle(record)
    return response(200).json(paginate(request, record.invoices))
  }),

  http.get('/api/v1/billing/usage/', ({ request, response }) => {
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    const { limits } = recordFor(ctx.workspace.id).subscription.plan
    const members = db.memberships.filter((membership) => membership.workspace_id === ctx.workspace.id).length
    return response(200).json({
      metrics: [
        { key: 'whatsapp_numbers', used: phoneNumbersFor(ctx.workspace.id).length, limit: limits.whatsapp_numbers },
        { key: 'members', used: members, limit: limits.members },
        { key: 'contacts', used: ctx.workspace.id === ids.sharmaSweets ? 48 : 0, limit: limits.contacts },
      ],
    })
  }),
]
