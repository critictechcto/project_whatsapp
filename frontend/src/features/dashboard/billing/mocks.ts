import type { Schemas } from '../../../api/types'
import { ANNUAL_MONTHS_CHARGED, plans as sitePlans, site } from '../../../config/site'
import { db } from '../../../mocks/db'
import { daysAgo, ids } from '../../../mocks/seed'
import { authorize, errorResponse, http, mockDelay, nowIso, paginate, uuid, validationError } from '../../../mocks/utils'
import type { AreaMockHandlers } from '../registry/types'
import { phoneNumbersFor } from '../whatsapp/mockState'
import { GST_STATES, GSTIN_PATTERN, normalizePhone, PHONE_PATTERN } from './gst'

/**
 * Billing handlers. New checkouts use `checkoutProvider` (Razorpay by default, like the backend's
 * `BILLING_PROVIDER`):
 * - Razorpay `payment_mode: 'autopay'` (the default): checkout returns a subscription session; verify
 *   marks the subscription `pending` and it turns `active` a few seconds later (like the Razorpay
 *   webhook), adding a GST invoice.
 * - Razorpay `payment_mode: 'one_time'`, and every Cashfree checkout: checkout returns an order
 *   session; verify (`razorpay_order_id`, or `order_id` for Cashfree) pays it at once, starting or
 *   extending a prepaid period and adding a GST invoice.
 * Switching: an active auto-pay plan can't buy anything (409 `subscription_active`); an active
 * one-time plan can pay once again (renew or change plan) but can't switch to auto-pay until it ends.
 */

type Plan = Schemas['Plan']
type Subscription = Schemas['Subscription']
type Profile = Schemas['BillingProfile']
type Invoice = Schemas['Invoice']
type Interval = Schemas['BillingIntervalEnum']
type Provider = Schemas['PaymentProviderEnum']
type PaymentMode = NonNullable<Subscription['payment_mode']>

/** Mock supplier state (Karnataka): same-state customers get CGST + SGST, others IGST. */
const SUPPLIER_STATE = '29'
const ACTIVATION_DELAY_MS = 6000
const DAY_MS = 86_400_000

let checkoutProvider: Provider = 'razorpay'

/** Test hook: which gateway new checkouts use (the backend's `BILLING_PROVIDER`). */
export function setMockCheckoutProvider(provider: Provider) {
  checkoutProvider = provider
}

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

type RazorpayCheckout = { provider: 'razorpay'; subscriptionId: string; plan: Plan; interval: Interval }
/** A one-time payment: a Razorpay order (`order_…`) or a Cashfree order (`upc_…`). */
type PrepaidOrder = { provider: Provider; orderId: string; plan: Plan; interval: Interval; paid: boolean }

type BillingRecord = {
  subscription: Subscription
  profile: Profile
  invoices: Invoice[]
  checkout: RazorpayCheckout | null
  orders: Map<string, PrepaidOrder>
  activateAt: number | null
}

const emptyProfile: Profile = {
  legal_name: '',
  gstin: '',
  email: '',
  phone: '',
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
    provider: null,
    payment_mode: null,
    auto_renews: false,
    gst_rate_percent: site.gstRate,
    checkout_provider: checkoutProvider,
  }
}

/** Razorpay subscriptions bill by calendar month or year. */
function addPeriod(start: Date, interval: Interval): Date {
  const end = new Date(start)
  if (interval === 'annual') end.setFullYear(end.getFullYear() + 1)
  else end.setMonth(end.getMonth() + 1)
  return end
}

/** Cashfree prepaid periods are 30 or 365 days (docs/contracts/billing-cashfree.md). */
function addPrepaidPeriod(start: Date, interval: Interval): Date {
  return new Date(start.getTime() + (interval === 'annual' ? 365 : 30) * DAY_MS)
}

function taxes(subtotal: number, stateCode: string) {
  if (stateCode === SUPPLIER_STATE) {
    const half = Math.round((subtotal * site.gstRate) / 200)
    return { cgst_paise: half, sgst_paise: half, igst_paise: 0, total_paise: subtotal + half * 2 }
  }
  const igst = Math.round((subtotal * site.gstRate) / 100)
  return { cgst_paise: 0, sgst_paise: 0, igst_paise: igst, total_paise: subtotal + igst }
}

const subtotalFor = (plan: Plan, interval: Interval) => (interval === 'annual' ? plan.annual_price_paise : plan.monthly_price_paise)

let invoiceSequence = 142

function makeInvoice(number: number, subtotal: number, stateCode: string, issuedAt: string, periodStart: string, periodEnd: string): Invoice {
  return {
    id: uuid(),
    number: `UPC/2026-27/${String(number).padStart(6, '0')}`,
    status: 'paid',
    issued_at: issuedAt,
    period_start: periodStart,
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
    subscription: trial(new Date(Date.now() + 9 * DAY_MS).toISOString()),
    profile: { ...emptyProfile },
    invoices: [],
    checkout: null,
    orders: new Map(),
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
      provider: 'cashfree',
      payment_mode: 'one_time',
      auto_renews: false,
      gst_rate_percent: site.gstRate,
      checkout_provider: checkoutProvider,
    },
    profile: {
      legal_name: 'Kaveri Dental Clinic LLP',
      gstin: '29AAKFK4821M1Z3',
      email: 'accounts@kaveridental.in',
      phone: '+919845012345',
      address_line1: '14, 2nd Cross, 80 Feet Road',
      address_line2: 'Indiranagar',
      city: 'Bengaluru',
      state_code: '29',
      postal_code: '560038',
    },
    invoices: [
      makeInvoice(142, starter.annual_price_paise, '29', daysAgo(40), daysAgo(40), daysAgo(-325)),
      makeInvoice(87, starter.monthly_price_paise, '29', daysAgo(71), daysAgo(71), daysAgo(41)),
    ],
    checkout: null,
    orders: new Map(),
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
      subscription: trial(new Date(created + site.trialDays * DAY_MS).toISOString()),
      profile: { ...emptyProfile },
      invoices: [],
      checkout: null,
      orders: new Map(),
      activateAt: null,
    }
    records.set(workspaceId, record)
  }
  return record
}

/** The subscription as the API returns it: derived fields follow the current state. */
function present(subscription: Subscription): Subscription {
  return {
    ...subscription,
    auto_renews: subscription.payment_mode === 'autopay' && subscription.status === 'active' && !subscription.cancel_at_period_end,
    gst_rate_percent: site.gstRate,
    checkout_provider: checkoutProvider,
  }
}

/** Simulates the Razorpay `subscription.charged` webhook arriving after verify. */
function settle(record: BillingRecord) {
  if (record.subscription.status !== 'pending' || record.activateAt === null || Date.now() < record.activateAt || !record.checkout) return
  const { plan, interval } = record.checkout
  const start = new Date()
  const end = addPeriod(start, interval)
  record.subscription = {
    ...record.subscription,
    plan,
    status: 'active',
    interval,
    trial_ends_at: null,
    current_period_start: start.toISOString(),
    current_period_end: end.toISOString(),
    cancel_at_period_end: false,
    provider: 'razorpay',
    payment_mode: 'autopay',
  }
  invoiceSequence += 1
  record.invoices.unshift(
    makeInvoice(invoiceSequence, subtotalFor(plan, interval), record.profile.state_code, start.toISOString(), start.toISOString(), end.toISOString()),
  )
  record.checkout = null
  record.activateAt = null
}

/** Fulfils a paid one-time order: same plan while active extends from the current end, anything else starts now. */
function fulfil(record: BillingRecord, order: PrepaidOrder) {
  const now = new Date()
  const current = record.subscription
  const extend =
    current.status === 'active' &&
    current.payment_mode === 'one_time' &&
    current.plan.id === order.plan.id &&
    current.interval === order.interval &&
    current.current_period_end !== null &&
    new Date(current.current_period_end).getTime() > now.getTime()
  const periodStart = extend ? new Date(current.current_period_end!) : now
  const periodEnd = addPrepaidPeriod(periodStart, order.interval)
  record.subscription = {
    ...current,
    plan: order.plan,
    interval: order.interval,
    status: 'active',
    trial_ends_at: current.trial_ends_at,
    current_period_start: extend ? current.current_period_start : now.toISOString(),
    current_period_end: periodEnd.toISOString(),
    cancel_at_period_end: false,
    provider: order.provider,
    payment_mode: 'one_time',
  }
  invoiceSequence += 1
  record.invoices.unshift(
    makeInvoice(
      invoiceSequence,
      subtotalFor(order.plan, order.interval),
      record.profile.state_code,
      now.toISOString(),
      periodStart.toISOString(),
      periodEnd.toISOString(),
    ),
  )
  order.paid = true
}

/** Stores phone numbers as E.164; Indian 10-digit numbers get +91. */
function toE164(value: string): string {
  const phone = normalizePhone(value)
  return /^\d{10}$/.test(phone) ? `+91${phone}` : phone
}

function profileErrors(profile: Profile): Record<string, string[]> {
  const errors: Record<string, string[]> = {}
  const required = ['legal_name', 'email', 'address_line1', 'city', 'state_code', 'postal_code'] as const
  for (const key of required) if (!profile[key].trim()) errors[key] = ['This field may not be blank.']
  if (profile.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(profile.email)) errors.email = ['Enter a valid email address.']
  if (profile.phone && !PHONE_PATTERN.test(profile.phone)) errors.phone = ['Enter a 10-digit Indian mobile number or an E.164 number.']
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

const verificationFailed = () =>
  errorResponse(400, 'payment_verification_failed', `We couldn't verify this payment. If money was deducted, contact ${site.email.support}.`)

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
    return response(200).json(present(record.subscription))
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
    if (body.payment_mode !== undefined && body.payment_mode !== 'autopay' && body.payment_mode !== 'one_time') {
      errors.payment_mode = [`"${String(body.payment_mode)}" is not a valid choice.`]
    }
    if (Object.keys(errors).length || !plan || !body.interval) return response.untyped(validationError(errors))
    const cashfree = checkoutProvider === 'cashfree'
    const paymentMode: PaymentMode = cashfree ? 'one_time' : (body.payment_mode ?? 'autopay')
    if (!isComplete(record.profile) || (cashfree && !record.profile.phone)) {
      return response.untyped(
        errorResponse(
          409,
          'billing_profile_required',
          cashfree
            ? 'Add your billing details, including a phone number, before subscribing.'
            : 'Add your billing details before subscribing.',
        ),
      )
    }
    const { subscription } = record
    if (subscription.status === 'active' && subscription.payment_mode !== 'one_time') {
      return response.untyped(
        errorResponse(
          409,
          'subscription_active',
          paymentMode === 'one_time'
            ? 'Your plan renews by auto-pay. Cancel auto-pay first; you can pay once after the current period ends.'
            : 'You already have an active subscription.',
        ),
      )
    }
    if (subscription.status === 'active' && paymentMode === 'autopay') {
      return response.untyped(errorResponse(409, 'subscription_active', 'You can switch to auto-pay when your paid period ends.'))
    }
    const common = {
      name: site.name,
      description: `${plan.name} plan, billed ${body.interval}`,
      prefill: { name: ctx.user.full_name ?? '', email: record.profile.email || ctx.user.email },
    }
    const amountPaise = taxes(subtotalFor(plan, body.interval), record.profile.state_code).total_paise
    if (cashfree) {
      const orderId = `upc_${uuid().replace(/-/g, '')}`
      record.orders.set(orderId, { provider: 'cashfree', orderId, plan, interval: body.interval, paid: false })
      return response(200).json({
        provider: 'cashfree',
        payment_mode: 'one_time',
        ...common,
        key_id: null,
        subscription_id: null,
        order_id: orderId,
        payment_session_id: `session_mock${uuid().replace(/-/g, '')}`,
        mode: 'sandbox',
        amount_paise: amountPaise,
      })
    }
    if (paymentMode === 'one_time') {
      const orderId = `order_mock${uuid().replace(/-/g, '').slice(0, 14)}`
      record.orders.set(orderId, { provider: 'razorpay', orderId, plan, interval: body.interval, paid: false })
      return response(200).json({
        provider: 'razorpay',
        payment_mode: 'one_time',
        ...common,
        key_id: 'rzp_test_mock',
        subscription_id: null,
        order_id: orderId,
        payment_session_id: null,
        mode: null,
        amount_paise: amountPaise,
      })
    }
    const subscriptionId = `sub_mock${uuid().replace(/-/g, '').slice(0, 14)}`
    record.checkout = { provider: 'razorpay', subscriptionId, plan, interval: body.interval }
    return response(200).json({
      provider: 'razorpay',
      payment_mode: 'autopay',
      ...common,
      key_id: 'rzp_test_mock',
      subscription_id: subscriptionId,
      order_id: null,
      payment_session_id: null,
      mode: null,
      amount_paise: null,
    })
  }),

  http.post('/api/v1/billing/subscription/verify/', async ({ request, response }) => {
    await mockDelay()
    const ctx = authorize(request, 'owner')
    if (ctx instanceof Response) return response.untyped(ctx)
    const record = recordFor(ctx.workspace.id)
    const body = (await request.json()) as Partial<Schemas['CheckoutVerifyRequest']>
    if (body.order_id !== undefined) {
      const order = record.orders.get(body.order_id)
      if (!order || order.provider !== 'cashfree') return response.untyped(verificationFailed())
      // Verify is idempotent: an order that was already paid returns the subscription unchanged.
      if (!order.paid) fulfil(record, order)
      return response(200).json(present(record.subscription))
    }
    if (body.razorpay_order_id !== undefined) {
      const order = record.orders.get(body.razorpay_order_id)
      if (!order || order.provider !== 'razorpay' || !body.razorpay_payment_id || !body.razorpay_signature) {
        return response.untyped(verificationFailed())
      }
      // Verify is idempotent: an order that was already paid returns the subscription unchanged.
      if (!order.paid) fulfil(record, order)
      return response(200).json(present(record.subscription))
    }
    if (
      !record.checkout ||
      body.razorpay_subscription_id !== record.checkout.subscriptionId ||
      !body.razorpay_payment_id ||
      !body.razorpay_signature
    ) {
      return response.untyped(verificationFailed())
    }
    record.subscription = { ...record.subscription, plan: record.checkout.plan, interval: record.checkout.interval, status: 'pending' }
    record.activateAt = Date.now() + ACTIVATION_DELAY_MS
    return response(200).json(present(record.subscription))
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
    return response(200).json(present(record.subscription))
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
    next.phone = next.phone ? toE164(next.phone) : ''
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
