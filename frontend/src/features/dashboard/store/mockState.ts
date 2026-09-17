/**
 * In-memory store, payments and seller-alert data for mock mode and tests, rebuilt whenever the
 * shared mock database is reset (before each test).
 */
import type { Schemas } from '../../../api/types'
import { db, type Mutable } from '../../../mocks/db'
import { daysAgo, ids, seedPhoneNumber, seedTemplates } from '../../../mocks/seed'

export type MockStoreSettings = Mutable<Schemas['StoreSettings']> & { notification_templates: Schemas['OrderNotificationTemplates'] }
export type MockPaymentAccount = Mutable<Schemas['PaymentAccount']> & {
  /** Kept only in the mock; never returned. */
  key_secret: string
  webhook_secret: string
  webhook_token: string
}
export type MockRecipient = Mutable<Schemas['AlertRecipient']> & { events: Schemas['AlertEventEnum'][] }

export type WorkspaceStore = {
  settings: MockStoreSettings
  account: MockPaymentAccount
  recipients: MockRecipient[]
  /** Active products in the catalog (the catalog area owns the real list). */
  activeProducts: number
  /** Starter template names already created in the WABA. */
  starterTemplates: string[]
}

export const PLATFORM_DISPLAY_NUMBER = '+91 80 6912 4400'
export const STARTER_TEMPLATE_NAMES = [
  'upc_order_confirmed',
  'upc_order_packed',
  'upc_order_shipped',
  'upc_order_delivered',
  'upc_order_cancelled',
  'upc_payment_reminder',
] as const

export const recipientIds = {
  rohit: 'e1a7c000-0000-4000-8000-000000000001',
  priya: 'e1a7c000-0000-4000-8000-000000000002',
} as const

export const DEFAULT_MENU_KEYWORDS = ['hi', 'hello', 'menu', 'shop', 'start']

export function webhookEvents(provider: Schemas['PaymentProviderEnum']): string[] {
  return provider === 'cashfree'
    ? ['PAYMENT_LINK_EVENT']
    : ['payment_link.paid', 'payment_link.partially_paid', 'payment_link.expired', 'payment_link.cancelled']
}

export function emptyAccount(provider: Schemas['PaymentProviderEnum'] = 'razorpay'): MockPaymentAccount {
  return {
    provider,
    mode: null,
    key_id: '',
    has_key_secret: false,
    has_webhook_secret: false,
    status: 'not_configured',
    verified_at: null,
    last_error: '',
    webhook_url: '',
    webhook_events: webhookEvents(provider),
    updated_at: null,
    key_secret: '',
    webhook_secret: '',
    webhook_token: '',
  }
}

function prefixFrom(name: string) {
  const letters = name
    .split(/\s+/)
    .map((word) => word[0] ?? '')
    .join('')
    .toUpperCase()
    .replace(/[^A-Z]/g, '')
  return (letters.length >= 2 ? letters : name.replace(/[^A-Za-z]/g, '').toUpperCase()).slice(0, 5).padEnd(2, 'X')
}

function defaultSettings(workspaceId: string): MockStoreSettings {
  const workspace = db.workspaces.find((candidate) => candidate.id === workspaceId)
  const name = workspace?.name ?? 'My store'
  const hasNumber = workspaceId === ids.sharmaSweets
  return {
    enabled: false,
    shop_mode: 'bot',
    store_name: name.slice(0, 60),
    welcome_message: `Welcome to ${name}! Browse our products and order right here on WhatsApp.`,
    menu_keywords: [...DEFAULT_MENU_KEYWORDS],
    order_prefix: prefixFrom(name),
    min_order_paise: 0,
    shipping_fee_paise: 0,
    free_shipping_above_paise: null,
    cod_enabled: false,
    cod_fee_paise: 0,
    cod_max_order_paise: null,
    serviceable_pincodes: [],
    support_message: 'Thanks for reaching out! Someone from our team will reply here shortly.',
    powered_by_footer: true,
    phone_number_id: null,
    store_link: hasNumber ? `https://wa.me/${seedPhoneNumber.phone_e164.slice(1)}?text=Hi` : null,
    notification_templates: { confirmed: null, packed: null, shipped: null, delivered: null, cancelled: null, payment_reminder: null },
    updated_at: daysAgo(3),
  }
}

function build(): Map<string, WorkspaceStore> {
  const sharma = defaultSettings(ids.sharmaSweets)
  Object.assign(sharma, {
    welcome_message: 'Namaste! Welcome to *Sharma Sweets*, Jaipur. Fresh mithai and namkeen, delivered to your door.',
    order_prefix: 'SS',
    min_order_paise: 29_900,
    shipping_fee_paise: 6_000,
    free_shipping_above_paise: 99_900,
    cod_enabled: true,
    cod_fee_paise: 2_000,
    cod_max_order_paise: 300_000,
    serviceable_pincodes: ['302001', '302004', '302017'],
    support_message: 'Thanks for writing to Sharma Sweets. Priya from our team will reply within an hour (10 am to 7 pm).',
    notification_templates: { ...sharma.notification_templates, shipped: seedTemplates[0].id },
  })

  const account = emptyAccount('razorpay')
  Object.assign(account, {
    mode: 'test',
    key_id: 'rzp_test_Sh4rmaSw33ts01',
    status: 'unverified',
    webhook_token: 'whk_sharma_0001',
    webhook_url: 'https://api.upchatz.com/webhooks/payments/merchants/whk_sharma_0001/',
    updated_at: daysAgo(2),
  })

  return new Map([
    [
      ids.sharmaSweets,
      {
        settings: sharma,
        account,
        activeProducts: 12,
        starterTemplates: [],
        recipients: [
          {
            id: recipientIds.rohit,
            name: 'Rohit Sharma',
            phone_e164: '+919829012345',
            status: 'verified',
            events: ['new_order', 'needs_attention', 'order_cancelled'],
            verified_at: daysAgo(9),
            last_sent_at: daysAgo(1),
            created_at: daysAgo(10),
          },
        ],
      },
    ],
  ])
}

let snapshot: { token: unknown; stores: Map<string, WorkspaceStore>; platform: Mutable<Schemas['PlatformAlertsInfo']> } | null = null

function state() {
  if (!snapshot || snapshot.token !== db.generation) {
    snapshot = { token: db.generation, stores: build(), platform: { available: true, display_phone_number: PLATFORM_DISPLAY_NUMBER } }
  }
  return snapshot
}

/** The store data of a workspace, created lazily like the backend's `StoreSettings`. */
export function storeState(workspaceId: string): WorkspaceStore {
  const { stores } = state()
  let entry = stores.get(workspaceId)
  if (!entry) {
    entry = { settings: defaultSettings(workspaceId), account: emptyAccount(), recipients: [], activeProducts: 0, starterTemplates: [] }
    stores.set(workspaceId, entry)
  }
  return entry
}

/** The UpChatz alerts number, shared by every workspace. Tests flip `available`. */
export function platformState() {
  return state().platform
}
