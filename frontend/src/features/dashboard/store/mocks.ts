import type { Schemas } from '../../../api/types'
import { ids, seedPhoneNumber } from '../../../mocks/seed'
import { mockRealtime } from '../../../mocks/realtime'
import { authorize, errorResponse, http, mockDelay, notFound, nowIso, paginate, uuid, validationError } from '../../../mocks/utils'
import type { AreaMockHandlers } from '../registry/types'
import type { StoreSettings, StoreSettingsPatch } from './api'
import {
  BOOKING_TEMPLATE_FIELDS,
  emptyAccount,
  platformState,
  STARTER_TEMPLATE_NAMES,
  storeState,
  webhookEvents,
  type MockPaymentAccount,
  type MockRecipient,
  type WorkspaceStore,
} from './mockState'

/**
 * Mock handlers for `/api/v1/store/`, `/api/v1/payments/` and `/api/v1/seller-alerts/`, with the
 * backend's validation and 409 codes. Verification succeeds for `rzp_test_…` Razorpay keys and
 * `TEST…` Cashfree App IDs; any other key is rejected as invalid.
 */

const PREFIX = /^[A-Z]{2,5}$/
const PINCODE = /^[1-9]\d{5}$/
const RAZORPAY_KEY = /^rzp_(test|live)_[A-Za-z0-9]+$/
const E164 = /^\+[1-9]\d{7,14}$/
const ALERT_EVENTS: readonly Schemas['AlertEventEnum'][] = ['new_order', 'new_booking', 'needs_attention', 'order_cancelled']
const MAX_RECIPIENTS = 3
const RESEND_COOLDOWN_MS = 5 * 60_000
const WEBHOOK_BASE = 'https://api.upchatz.com/webhooks/payments/merchants'

const providerNames = { razorpay: 'Razorpay', cashfree: 'Cashfree' } as const

function hasNumber(workspaceId: string) {
  return workspaceId === ids.sharmaSweets
}

function isMoney(value: unknown) {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0
}


function settingsResponse(store: WorkspaceStore): Schemas['StoreSettings'] {
  const { settings } = store
  const body: StoreSettings = {
    ...settings,
    menu_keywords: [...(settings.menu_keywords ?? [])],
    serviceable_pincodes: [...(settings.serviceable_pincodes ?? [])],
    notification_templates: { ...settings.notification_templates },
    booking_days: [...settings.booking_days],
    booking_windows: settings.booking_windows.map((window) => ({ ...window })),
  }
  return body
}

const TIME = /^([01]\d|2[0-3]):[0-5]\d$/

function isWholeNumber(value: unknown, min: number, max: number) {
  return typeof value === 'number' && Number.isInteger(value) && value >= min && value <= max
}

function bookingErrors(body: StoreSettingsPatch): Record<string, string[]> {
  const errors: Record<string, string[]> = {}
  if (body.booking_days !== undefined) {
    if (!body.booking_days.length) errors.booking_days = ['Choose at least one day.']
    else if (body.booking_days.some((day) => !isWholeNumber(day, 0, 6))) errors.booking_days = ['Days are numbers from 0 (Monday) to 6 (Sunday).']
  }
  if (body.booking_windows !== undefined) {
    const windows = body.booking_windows
    if (windows.length < 1 || windows.length > 10) errors.booking_windows = ['Use 1 to 10 time windows.']
    else {
      const bad = windows.find(
        (window) => !window.label.trim() || window.label.length > 24 || !TIME.test(window.start) || !TIME.test(window.end) || window.start >= window.end,
      )
      if (bad) errors.booking_windows = [`“${bad.label}” needs a name of up to 24 characters and an end after its start.`]
    }
  }
  if (body.booking_days_ahead !== undefined && !isWholeNumber(body.booking_days_ahead, 1, 30)) {
    errors.booking_days_ahead = ['Ensure this value is between 1 and 30.']
  }
  if (body.booking_reminder_hours !== undefined && !isWholeNumber(body.booking_reminder_hours, 0, 48)) {
    errors.booking_reminder_hours = ['Ensure this value is between 0 and 48.']
  }
  if (body.booking_day_before_reminder !== undefined && typeof body.booking_day_before_reminder !== 'boolean') {
    errors.booking_day_before_reminder = ['Must be a valid boolean.']
  }
  return errors
}

function checklist(workspaceId: string, store: WorkspaceStore): Schemas['StoreChecklist'] {
  const { settings, account, recipients, activeProducts, activeServices } = store
  const mapped = Object.values(settings.notification_templates).filter(Boolean).length
  const bookingMapped = BOOKING_TEMPLATE_FIELDS.filter((field) => settings[field]).length
  const bookingStep: Schemas['StoreChecklistItem'][] =
    activeServices > 0
      ? [
          {
            key: 'booking_templates',
            done: bookingMapped === 3,
            detail: bookingMapped === 3 ? 'Every booking update has a template.' : `${bookingMapped} of 3 booking updates have a template.`,
          },
        ]
      : []
  const verifiedGateway = account.status === 'verified'
  const verifiedRecipients = recipients.filter((recipient) => recipient.status === 'verified')
  const paymentsDetail = verifiedGateway
    ? `${providerNames[account.provider ?? 'razorpay']} is connected (${account.mode === 'live' ? 'live' : 'test'} mode).`
    : settings.cod_enabled
      ? 'Cash on delivery is on. Connect Razorpay or Cashfree to take online payments too.'
      : 'Connect Razorpay or Cashfree, or turn on cash on delivery.'
  return {
    items: [
      {
        key: 'whatsapp_connected',
        done: hasNumber(workspaceId),
        detail: hasNumber(workspaceId) ? `${seedPhoneNumber.display_phone_number} is connected.` : 'Connect the WhatsApp number buyers will message.',
      },
      {
        key: 'products_added',
        done: activeProducts > 0,
        detail: activeProducts > 0 ? `${activeProducts} active products.` : 'Add at least one product buyers can order.',
      },
      { key: 'payments_configured', done: verifiedGateway || Boolean(settings.cod_enabled), detail: paymentsDetail },
      {
        key: 'order_templates_ready',
        done: mapped === 6,
        detail: mapped === 6 ? 'Every order update has a template.' : `${mapped} of 6 order updates have a template.`,
      },
      ...bookingStep,
      {
        key: 'alert_number_verified',
        done: verifiedRecipients.length > 0,
        detail: verifiedRecipients.length
          ? `Alerts go to ${verifiedRecipients.map((recipient) => recipient.name).join(', ')}.`
          : 'Add and confirm the number that gets new-order alerts.',
      },
      {
        key: 'store_enabled',
        done: Boolean(settings.enabled),
        detail: settings.enabled ? 'Buyers can shop now.' : 'Turn on the store when you are ready to sell.',
      },
    ],
  }
}

function settingsErrors(workspaceId: string, body: Schemas['PatchedStoreSettingsRequest']): Record<string, string[]> {
  const errors: Record<string, string[]> = {}
  if (body.store_name !== undefined) {
    const name = body.store_name.trim()
    if (!name) errors.store_name = ['This field may not be blank.']
    else if (name.length > 60) errors.store_name = ['Ensure this field has no more than 60 characters.']
  }
  if (body.welcome_message !== undefined && body.welcome_message.length > 1024) {
    errors.welcome_message = ['Ensure this field has no more than 1024 characters.']
  }
  if (body.support_message !== undefined && body.support_message.length > 1024) {
    errors.support_message = ['Ensure this field has no more than 1024 characters.']
  }
  if (body.order_prefix !== undefined && !PREFIX.test(body.order_prefix)) {
    errors.order_prefix = ['Use 2 to 5 capital letters (A–Z).']
  }
  for (const key of ['min_order_paise', 'shipping_fee_paise', 'cod_fee_paise'] as const) {
    if (body[key] !== undefined && !isMoney(body[key])) errors[key] = ['Ensure this value is greater than or equal to 0.']
  }
  for (const key of ['free_shipping_above_paise', 'cod_max_order_paise'] as const) {
    if (body[key] !== undefined && body[key] !== null && !isMoney(body[key])) errors[key] = ['Ensure this value is greater than or equal to 0.']
  }
  if (body.menu_keywords !== undefined) {
    if (body.menu_keywords.some((keyword) => !keyword.trim())) errors.menu_keywords = ['Keywords may not be blank.']
    else if (body.menu_keywords.length > 20) errors.menu_keywords = ['Use at most 20 keywords.']
  }
  if (body.serviceable_pincodes !== undefined) {
    const bad = body.serviceable_pincodes.find((pincode) => !PINCODE.test(pincode))
    if (bad !== undefined) errors.serviceable_pincodes = [`“${bad}” is not a valid 6-digit pincode.`]
  }
  if (body.phone_number_id && !(hasNumber(workspaceId) && body.phone_number_id === seedPhoneNumber.id)) {
    errors.phone_number_id = ['Choose a number connected to this workspace.']
  }
  return errors
}

function toAccount(account: MockPaymentAccount): Schemas['PaymentAccount'] {
  const { key_secret: _secret, webhook_secret: _webhookSecret, webhook_token: _token, ...rest } = account
  return { ...rest, webhook_events: [...rest.webhook_events] }
}

function toRecipient(recipient: MockRecipient): Schemas['AlertRecipient'] {
  return { ...recipient, events: [...recipient.events] }
}

function eventsErrors(events: unknown): string[] | null {
  if (!Array.isArray(events)) return ['Expected a list of items.']
  if (events.length === 0) return ['Choose at least one alert.']
  const bad = events.find((event) => !ALERT_EVENTS.includes(event as Schemas['AlertEventEnum']))
  return bad === undefined ? null : [`“${String(bad)}” is not a valid choice.`]
}

export const handlers: AreaMockHandlers = [
  // Store
  http.get('/api/v1/store/settings/', ({ request, response }) => {
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    return response(200).json(settingsResponse(storeState(ctx.workspace.id)))
  }),

  http.patch('/api/v1/store/settings/', async ({ request, response }) => {
    await mockDelay()
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const store = storeState(ctx.workspace.id)
    const body = (await request.json()) as StoreSettingsPatch
    const errors = { ...settingsErrors(ctx.workspace.id, body), ...bookingErrors(body) }
    if (Object.keys(errors).length) return response.untyped(validationError(errors))

    if (body.shop_mode === 'native_catalog' && store.settings.shop_mode !== 'native_catalog') {
      return response.untyped(
        errorResponse(409, 'catalog_not_connected', 'Connect a Meta catalog on the Catalog page before choosing native catalog mode.'),
      )
    }
    if (body.enabled && !store.settings.enabled) {
      const missing = [
        !hasNumber(ctx.workspace.id) && 'connect a WhatsApp number',
        store.activeProducts === 0 && 'add at least one active product',
      ].filter(Boolean)
      if (missing.length) {
        return response.untyped(errorResponse(409, 'commerce_not_enabled', `To turn on the store, ${missing.join(' and ')}.`))
      }
    }

    const { notification_templates: templates, booking_days: days, booking_windows: windows, ...fields } = body
    Object.assign(store.settings, fields)
    if (days) store.settings.booking_days = [...new Set(days)].sort((a, b) => a - b)
    if (windows) store.settings.booking_windows = windows.map(({ label, start, end }) => ({ label: label.trim(), start, end }))
    if (typeof fields.store_name === 'string') store.settings.store_name = fields.store_name.trim()
    if (templates) store.settings.notification_templates = { ...store.settings.notification_templates, ...templates }
    store.settings.updated_at = nowIso()
    return response(200).json(settingsResponse(store))
  }),

  http.get('/api/v1/store/checklist/', ({ request, response }) => {
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    return response(200).json(checklist(ctx.workspace.id, storeState(ctx.workspace.id)))
  }),

  http.post('/api/v1/store/starter-templates/', async ({ request, response }) => {
    await mockDelay(600)
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    if (!hasNumber(ctx.workspace.id)) {
      return response.untyped(errorResponse(409, 'whatsapp_not_connected', 'Connect a WhatsApp number before creating templates.'))
    }
    const store = storeState(ctx.workspace.id)
    const existing = STARTER_TEMPLATE_NAMES.filter((name) => store.starterTemplates.includes(name))
    const created = STARTER_TEMPLATE_NAMES.filter((name) => !store.starterTemplates.includes(name))
    store.starterTemplates.push(...created)
    return response(200).json({ created, existing })
  }),

  // Payments
  http.get('/api/v1/payments/account/', ({ request, response }) => {
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    return response(200).json(toAccount(storeState(ctx.workspace.id).account))
  }),

  http.patch('/api/v1/payments/account/', async ({ request, response }) => {
    await mockDelay()
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const store = storeState(ctx.workspace.id)
    const current = store.account
    const body = (await request.json()) as Schemas['PatchedPaymentAccountRequest']
    const errors: Record<string, string[]> = {}

    const switching = body.provider !== undefined && body.provider !== current.provider
    const next: MockPaymentAccount = switching ? { ...emptyAccount(body.provider), webhook_token: current.webhook_token } : { ...current }
    const provider = next.provider ?? 'razorpay'
    let credentialsChanged = switching

    if (body.key_id !== undefined) {
      const keyId = body.key_id.trim()
      if (provider === 'razorpay' && !RAZORPAY_KEY.test(keyId)) {
        errors.key_id = ['Enter a Razorpay key id that starts with rzp_test_ or rzp_live_.']
      } else if (!keyId) {
        errors.key_id = ['This field may not be blank.']
      } else if (keyId !== next.key_id) {
        next.key_id = keyId
        credentialsChanged = true
        if (provider === 'razorpay') next.mode = keyId.startsWith('rzp_live_') ? 'live' : 'test'
      }
    }
    if (body.mode !== undefined) {
      if (provider === 'razorpay') {
        if (body.mode !== null && next.key_id && body.mode !== next.mode) errors.mode = [`This key is for ${next.mode} mode.`]
      } else if (body.mode !== next.mode) {
        next.mode = body.mode
        credentialsChanged = true
      }
    }
    if (body.key_secret !== undefined) {
      if (!body.key_secret.trim()) errors.key_secret = ['This field may not be blank.']
      else {
        next.key_secret = body.key_secret
        next.has_key_secret = true
        credentialsChanged = true
      }
    }
    if (body.webhook_secret !== undefined) {
      if (provider !== 'razorpay') errors.webhook_secret = ['Cashfree signs webhooks with your secret key, so no webhook secret is needed.']
      else {
        next.webhook_secret = body.webhook_secret
        next.has_webhook_secret = Boolean(body.webhook_secret)
      }
    }
    if (Object.keys(errors).length) return response.untyped(validationError(errors))

    if (credentialsChanged) {
      next.status = next.key_id ? 'unverified' : 'not_configured'
      next.verified_at = null
      next.last_error = ''
    }
    if (next.key_id && !next.webhook_token) next.webhook_token = `whk_${uuid().slice(0, 12)}`
    next.webhook_url = next.key_id ? `${WEBHOOK_BASE}/${next.webhook_token}/` : ''
    next.webhook_events = webhookEvents(provider)
    next.updated_at = nowIso()
    Object.assign(current, next)
    return response(200).json(toAccount(current))
  }),

  http.delete('/api/v1/payments/account/', async ({ request, response }) => {
    await mockDelay()
    const ctx = authorize(request, 'owner')
    if (ctx instanceof Response) return response.untyped(ctx)
    const store = storeState(ctx.workspace.id)
    store.account = emptyAccount()
    return response(204).empty()
  }),

  http.post('/api/v1/payments/account/verify/', async ({ request, response }) => {
    await mockDelay(700)
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const account = storeState(ctx.workspace.id).account
    const provider = account.provider ?? 'razorpay'
    const name = providerNames[provider]
    if (!account.key_id || !account.has_key_secret) {
      return response.untyped(errorResponse(409, 'payment_account_missing', `Save your ${name} key id and secret before verifying.`))
    }
    if (provider === 'cashfree' && !account.mode) {
      return response.untyped(validationError({ mode: ['Choose Test or Live before verifying.'] }))
    }
    const valid = provider === 'razorpay' ? account.key_id.startsWith('rzp_test_') : account.key_id.startsWith('TEST')
    if (valid) {
      Object.assign(account, { status: 'verified', verified_at: nowIso(), last_error: '', updated_at: nowIso() })
      return response(200).json(toAccount(account))
    }
    const message =
      provider === 'razorpay'
        ? 'Razorpay rejected these keys (401 Unauthorized). Check the key id and secret under Account & Settings → API Keys.'
        : 'Cashfree rejected these credentials (401). Check the App ID and secret key, and that Test or Live matches where you copied them from.'
    Object.assign(account, { status: 'invalid', verified_at: null, last_error: message, updated_at: nowIso() })
    return response.untyped(errorResponse(409, 'payment_account_invalid', message))
  }),

  http.post('/api/v1/payments/account/rotate-webhook/', async ({ request, response }) => {
    await mockDelay()
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const account = storeState(ctx.workspace.id).account
    if (!account.key_id) {
      return response.untyped(errorResponse(409, 'payment_account_missing', 'Save your gateway keys before setting up a webhook.'))
    }
    account.webhook_token = `whk_${uuid().slice(0, 12)}`
    account.webhook_url = `${WEBHOOK_BASE}/${account.webhook_token}/`
    account.updated_at = nowIso()
    return response(200).json(toAccount(account))
  }),

  // Seller alerts
  http.get('/api/v1/seller-alerts/platform/', ({ request, response }) => {
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    const platform = platformState()
    return response(200).json({ available: platform.available, display_phone_number: platform.available ? platform.display_phone_number : '' })
  }),

  http.get('/api/v1/seller-alerts/recipients/', ({ request, response }) => {
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    const items = [...storeState(ctx.workspace.id).recipients].sort((a, b) => a.created_at.localeCompare(b.created_at)).map(toRecipient)
    return response(200).json(paginate(request, items))
  }),

  http.post('/api/v1/seller-alerts/recipients/', async ({ request, response }) => {
    await mockDelay(500)
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const workspaceId = ctx.workspace.id
    const store = storeState(workspaceId)
    if (!platformState().available) {
      return response.untyped(errorResponse(409, 'platform_alerts_unavailable', "Order alerts on WhatsApp aren't available yet."))
    }
    const body = (await request.json()) as Partial<Schemas['AlertRecipientRequest']>
    const errors: Record<string, string[]> = {}
    const name = (body.name ?? '').trim()
    if (!name) errors.name = ['This field may not be blank.']
    else if (name.length > 60) errors.name = ['Ensure this field has no more than 60 characters.']
    const phone = (body.phone_e164 ?? '').trim()
    if (!E164.test(phone)) errors.phone_e164 = ['Enter a valid phone number in international format, like +919876543210.']
    else if (store.recipients.some((recipient) => recipient.phone_e164 === phone)) {
      errors.phone_e164 = ['This number already gets alerts for this workspace.']
    }
    if (body.events !== undefined) {
      const eventErrors = eventsErrors(body.events)
      if (eventErrors) errors.events = eventErrors
    }
    if (Object.keys(errors).length) return response.untyped(validationError(errors))
    if (store.recipients.length >= MAX_RECIPIENTS) {
      return response.untyped(
        errorResponse(409, 'alert_recipient_limit', `You can have up to ${MAX_RECIPIENTS} alert numbers. Remove one to add another.`),
      )
    }

    const now = nowIso()
    const recipient: MockRecipient = {
      id: uuid(),
      name,
      phone_e164: phone,
      status: 'pending',
      events: body.events ? [...body.events] : [...ALERT_EVENTS],
      verified_at: null,
      last_sent_at: now,
      created_at: now,
    }
    store.recipients.push(recipient)

    // In the browser demo the seller "taps Confirm" a few seconds later.
    if (import.meta.env.MODE !== 'test') {
      setTimeout(() => {
        if (!store.recipients.includes(recipient) || recipient.status !== 'pending') return
        recipient.status = 'verified'
        recipient.verified_at = nowIso()
        mockRealtime.emit('alert_recipient.updated', { recipient_id: recipient.id, status: 'verified' }, workspaceId)
      }, 5_000)
    }
    return response(201).json(toRecipient(recipient))
  }),

  http.patch('/api/v1/seller-alerts/recipients/{id}/', async ({ request, params, response }) => {
    await mockDelay()
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const recipient = storeState(ctx.workspace.id).recipients.find((candidate) => candidate.id === params.id)
    if (!recipient) return response.untyped(notFound())
    const body = (await request.json()) as Schemas['PatchedAlertRecipientRequest']
    const errors: Record<string, string[]> = {}
    if (body.name !== undefined) {
      const name = body.name.trim()
      if (!name) errors.name = ['This field may not be blank.']
      else if (name.length > 60) errors.name = ['Ensure this field has no more than 60 characters.']
    }
    if (body.phone_e164 !== undefined && body.phone_e164 !== recipient.phone_e164) errors.phone_e164 = ["The number can't be changed. Add a new recipient instead."]
    if (body.events !== undefined) {
      const eventErrors = eventsErrors(body.events)
      if (eventErrors) errors.events = eventErrors
    }
    if (Object.keys(errors).length) return response.untyped(validationError(errors))
    if (body.name !== undefined) recipient.name = body.name.trim()
    if (body.events !== undefined) recipient.events = [...body.events]
    return response(200).json(toRecipient(recipient))
  }),

  http.delete('/api/v1/seller-alerts/recipients/{id}/', async ({ request, params, response }) => {
    await mockDelay()
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const store = storeState(ctx.workspace.id)
    const index = store.recipients.findIndex((candidate) => candidate.id === params.id)
    if (index < 0) return response.untyped(notFound())
    store.recipients.splice(index, 1)
    return response(204).empty()
  }),

  http.post('/api/v1/seller-alerts/recipients/{id}/resend-verification/', async ({ request, params, response }) => {
    await mockDelay()
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const recipient = storeState(ctx.workspace.id).recipients.find((candidate) => candidate.id === params.id)
    if (!recipient) return response.untyped(notFound())
    if (recipient.status === 'verified') {
      return response.untyped(errorResponse(409, 'already_verified', 'This number is already confirmed.'))
    }
    if (recipient.last_sent_at && Date.now() - new Date(recipient.last_sent_at).getTime() < RESEND_COOLDOWN_MS) {
      return response.untyped(
        errorResponse(409, 'verification_recently_sent', 'We sent a confirmation less than 5 minutes ago. Please wait a few minutes before sending another.'),
      )
    }
    recipient.status = 'pending'
    recipient.last_sent_at = nowIso()
    return response(200).json(toRecipient(recipient))
  }),
]
