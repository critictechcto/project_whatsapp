/**
 * In-memory orders for mock mode and tests: Sharma Sweets orders in every status. Rebuilt whenever
 * the shared mock database is reset (tests reset it before each test).
 */
import type { Schemas } from '../../../api/types'
import { formatInZone } from '../../../lib/datetime'
import { formatPaise } from '../../../lib/money'
import { db, type Mutable } from '../../../mocks/db'
import { ids, indianMobile, indianName, seedPhoneNumber } from '../../../mocks/seed'
import { orderTransitions, stageStatuses } from './labels'

type Order = Schemas['Order']
type OrderStatus = Schemas['OrderStatusEnum']
type PaymentMethod = Schemas['PaymentMethodEnum']
type OrderSource = Schemas['OrderSourceEnum']
type EventType = Schemas['OrderEventTypeEnum']
type EventActor = Schemas['OrderEventActorEnum']

export type MockOrder = Mutable<Omit<Order, 'allowed_transitions'>>
export type MockOrderEvent = Mutable<Schemas['OrderEvent']>
export type OrderRecord = { workspaceId: string; order: MockOrder; events: MockOrderEvent[] }

const MINUTE = 60_000
const HOUR = 60 * MINUTE

/* ---------- Products (snapshots on order items) ---------- */

type MockProduct = { sku: string; name: string; price: number; color: string; image: boolean }

const products: MockProduct[] = [
  { sku: 'KAJU-KATLI-500', name: 'Kaju Katli (500 g)', price: 65_000, color: '#d9c7a1', image: true },
  { sku: 'MOTICHOOR-1KG', name: 'Motichoor Laddoo (1 kg)', price: 56_000, color: '#e7a13d', image: true },
  { sku: 'SOAN-PAPDI-500', name: 'Soan Papdi (500 g)', price: 24_000, color: '#e9d9a6', image: true },
  { sku: 'RASGULLA-TIN-1KG', name: 'Rasgulla tin (1 kg)', price: 32_000, color: '#efe9dc', image: false },
  { sku: 'GHEVAR-MALAI', name: 'Malai Ghevar', price: 45_000, color: '#c98b3c', image: true },
  { sku: 'DRYFRUIT-BOX', name: 'Dry fruit gift box', price: 145_000, color: '#8a5d3b', image: true },
  { sku: 'BESAN-LADDOO-500', name: 'Besan Laddoo (500 g)', price: 30_000, color: '#d9a74a', image: true },
  { sku: 'NAMKEEN-MIX-400', name: 'Jaipuri namkeen mix (400 g)', price: 18_000, color: '#b7832f', image: false },
  { sku: 'MILK-CAKE-500', name: 'Milk cake (500 g)', price: 42_000, color: '#caa27a', image: true },
  { sku: 'MAWA-KACHORI-6', name: 'Mawa kachori (6 pcs)', price: 24_000, color: '#b9772f', image: true },
  // Kabir's shop bot order in the inbox mock (SS-1042).
  { sku: 'SS-KAJU-250', name: 'Kaju Katli 250 g', price: 22_000, color: '#d9c7a1', image: true },
  { sku: 'SS-SOAN-250', name: 'Soan Papdi 250 g', price: 10_000, color: '#e9d9a6', image: false },
]

function productImage(product: MockProduct): string | null {
  if (!product.image) return null
  const initials = product.name
    .split(/\s+/)
    .slice(0, 2)
    .map((word) => word[0])
    .join('')
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96"><rect width="96" height="96" fill="${product.color}"/><circle cx="48" cy="52" r="26" fill="#fff" fill-opacity="0.35"/><text x="48" y="60" text-anchor="middle" font-family="sans-serif" font-size="24" font-weight="600" fill="#10271f">${initials}</text></svg>`
  return `data:image/svg+xml,${encodeURIComponent(svg)}`
}

/* ---------- Contacts and conversations (same ids as the inbox and contacts mocks) ---------- */

const CONTACT_PREFIX = 'e0f1a2b3-c4d5-4e6f-8a9b-'

/** Contact index → inbox mock conversation number. */
const conversationByContact: Record<number, number> = { 1: 1, 2: 2, 5: 3, 6: 10, 7: 5, 8: 6, 10: 7, 12: 9 }

function contact(i: number): Schemas['ConversationContact'] {
  return {
    id: `${CONTACT_PREFIX}${String(i + 1).padStart(12, '0')}`,
    name: indianName(i),
    phone_e164: indianMobile(i),
    marketing_opt_in_status: i % 9 === 4 ? 'opted_out' : i % 3 === 0 ? 'unknown' : 'opted_in',
  }
}

function conversationId(contactIndex: number): string | null {
  const n = conversationByContact[contactIndex]
  return n ? `c3d4e5f6-a7b8-4c9d-8e0f-${String(n).padStart(12, '0')}` : null
}

const places = [
  { street: 'Johari Bazaar', landmark: 'Near Hawa Mahal', city: 'Jaipur', state: 'Rajasthan', pincode: '302003' },
  { street: 'C-Scheme, Ashok Marg', landmark: 'Opposite Central Park', city: 'Jaipur', state: 'Rajasthan', pincode: '302001' },
  { street: 'Lajpat Nagar II', landmark: 'Behind Central Market', city: 'New Delhi', state: 'Delhi', pincode: '110024' },
  { street: 'Malviya Nagar, Sector 3', landmark: '', city: 'Jaipur', state: 'Rajasthan', pincode: '302017' },
  { street: 'Koregaon Park Lane 5', landmark: 'Near the German Bakery', city: 'Pune', state: 'Maharashtra', pincode: '411001' },
]

function address(contactIndex: number): Schemas['OrderAddress'] {
  const place = places[contactIndex % places.length]
  const person = contact(contactIndex)
  return {
    name: person.name,
    phone_e164: person.phone_e164,
    line1: `${12 + contactIndex * 3}, ${place.street}`,
    line2: contactIndex % 2 ? `Flat ${100 + contactIndex}` : '',
    landmark: place.landmark,
    city: place.city,
    state: place.state,
    pincode: place.pincode,
    country: 'IN',
  }
}

function userSummary(userId: string): Schemas['UserSummary'] | null {
  const user = db.users.find((candidate) => candidate.id === userId)
  return user ? { id: user.id, full_name: user.full_name ?? '', email: user.email } : null
}

/* ---------- Seeds ---------- */

type Seed = {
  key?: string
  /** Fixed id and number, for orders the inbox mock links to. */
  id?: string
  number?: string
  freeShipping?: boolean
  hoursAgo: number
  contact: number
  lines: [product: number, quantity: number][]
  status: OrderStatus
  method?: PaymentMethod
  source?: OrderSource
  /** For cancelled orders: the status they were cancelled from. */
  cancelledFrom?: 'pending_payment' | 'confirmed' | 'packed'
  cancelReason?: string
  refunded?: boolean
  codCollected?: boolean
  courier?: [name: string, awb: string, url: string]
  notifyShippedFailed?: boolean
  /** The order confirmation was sent but Meta later failed it with this error code. */
  confirmationFailedCode?: string
  priceChanged?: boolean
  notes?: string
}

/** Seeds in chronological order; numbers are assigned from SS-1001 in this order. */
const seeds: Seed[] = [
  ...Array.from({ length: 6 }, (_, k): Seed => ({
    hoursAgo: 420 - k * 36,
    contact: 24 + k,
    lines: [
      [k % products.length, 1 + (k % 2)],
      [(k + 3) % products.length, 1],
    ],
    status: 'delivered',
    method: k % 2 ? 'online' : 'cod',
    codCollected: true,
    source: k % 3 === 0 ? 'native_cart' : 'bot',
    courier: ['Delhivery', `DL${48213700 + k * 17}`, ''],
  })),
  { hoursAgo: 186, contact: 1, lines: [[0, 1], [2, 2]], status: 'delivered', method: 'cod', codCollected: true, courier: ['Delhivery', 'DL48213990', ''] },
  { hoursAgo: 170, contact: 2, lines: [[5, 1]], status: 'delivered', method: 'online', courier: ['Blue Dart', '90412257781', 'https://www.bluedart.com/tracking'] },
  {
    hoursAgo: 150,
    contact: 5,
    lines: [[4, 2]],
    status: 'cancelled',
    method: 'online',
    cancelledFrom: 'confirmed',
    cancelReason: 'Ghevar was sold out for the day.',
    refunded: true,
  },
  { hoursAgo: 130, contact: 7, lines: [[1, 1], [9, 1]], status: 'delivered', method: 'cod', codCollected: true, courier: ['Shree Maruti', 'SM7731045', ''] },
  { key: 'expired', hoursAgo: 120, contact: 14, lines: [[0, 2]], status: 'expired', method: 'online' },
  { hoursAgo: 100, contact: 8, lines: [[6, 2], [7, 1]], status: 'delivered', method: 'online', source: 'native_cart', courier: ['India Post', 'EK123456789IN', 'https://www.indiapost.gov.in/'] },
  { hoursAgo: 96, contact: 10, lines: [[8, 1]], status: 'delivered', method: 'cod', codCollected: true, courier: ['Delhivery', 'DL48214552', ''] },
  {
    key: 'cancelledWithLink',
    hoursAgo: 80,
    contact: 15,
    lines: [[5, 1], [0, 1]],
    status: 'cancelled',
    method: 'online',
    cancelledFrom: 'pending_payment',
    cancelReason: 'The buyer asked to cancel before paying.',
  },
  {
    key: 'shippedTracked',
    hoursAgo: 72,
    contact: 12,
    lines: [[5, 1], [2, 1]],
    status: 'shipped',
    method: 'online',
    courier: ['Blue Dart', '90412260014', 'https://www.bluedart.com/tracking'],
    notifyShippedFailed: true,
  },
  { key: 'shippedCod', hoursAgo: 60, contact: 1, lines: [[1, 2]], status: 'shipped', method: 'cod', courier: ['Delhivery', 'DL48215020', ''] },
  { key: 'deliveredCod', hoursAgo: 50, contact: 16, lines: [[3, 1], [7, 2]], status: 'delivered', method: 'cod', courier: ['Shree Maruti', 'SM7731876', ''] },
  {
    hoursAgo: 30,
    contact: 17,
    lines: [[9, 2]],
    status: 'cancelled',
    method: 'cod',
    cancelledFrom: 'confirmed',
    cancelReason: 'We don’t deliver to this pincode yet.',
  },
  { key: 'needsAttention', hoursAgo: 26, contact: 2, lines: [[0, 1], [4, 1]], status: 'needs_attention', method: 'online' },
  { key: 'packedCod', hoursAgo: 22, contact: 5, lines: [[6, 1], [2, 1]], status: 'packed', method: 'cod', notes: 'Pack in the Diwali gift box, buyer asked for extra bubble wrap.' },
  {
    key: 'cancelledPaid',
    hoursAgo: 20,
    contact: 18,
    lines: [[4, 3]],
    status: 'cancelled',
    method: 'online',
    cancelledFrom: 'confirmed',
    cancelReason: 'Out of stock: Malai Ghevar.',
  },
  { key: 'confirmedPaid', hoursAgo: 8, contact: 7, lines: [[5, 2]], status: 'confirmed', method: 'online', source: 'native_cart' },
  { key: 'confirmedCod', hoursAgo: 5, contact: 19, lines: [[1, 1], [8, 1]], status: 'confirmed', method: 'cod' },
  { hoursAgo: 3, contact: 10, lines: [[0, 1]], status: 'packed', method: 'online' },
  { hoursAgo: 1.5, contact: 12, lines: [[9, 1], [3, 1]], status: 'confirmed', method: 'cod' },
  {
    key: 'kabirShop',
    id: '7d0a4e3c-9f6b-4a1c-a5e8-3b4c5d6e7f01',
    number: 'SS-1042',
    hoursAgo: 1.15,
    contact: 6,
    lines: [
      [10, 2],
      [11, 1],
    ],
    status: 'confirmed',
    method: 'online',
    source: 'bot',
    freeShipping: true,
    confirmationFailedCode: '131042',
  },
  { hoursAgo: 0.6, contact: 20, lines: [[2, 2]], status: 'awaiting_payment_method' },
  { hoursAgo: 0.4, contact: 21, lines: [[6, 1], [1, 1]], status: 'awaiting_address', source: 'native_cart' },
  { hoursAgo: 0.3, contact: 22, lines: [[0, 1]], status: 'awaiting_confirmation', priceChanged: true, source: 'native_cart' },
  { key: 'pendingPayment', hoursAgo: 0.2, contact: 8, lines: [[5, 1], [8, 1]], status: 'pending_payment', method: 'online' },
  { hoursAgo: 0.1, contact: 23, lines: [[7, 1]], status: 'draft' },
]

const SHIPPING_PAISE = 6_000
const FREE_SHIPPING_ABOVE_PAISE = 99_900
const COD_FEE_PAISE = 3_000
const CHECKOUT_TTL_MINUTES = 35
const LINK_EXPIRY_MINUTES = 30

function orderId(n: number) {
  return `0d1e2f30-4a5b-4c6d-8e7f-${String(n).padStart(12, '0')}`
}

const ORDER_PREFIX = 'SS'

function buildRecord(workspaceId: string, n: number, seed: Seed, now: number): OrderRecord {
  const number = seed.number ?? `${ORDER_PREFIX}-${1000 + n}`
  const created = now - seed.hoursAgo * HOUR
  let t = created
  const iso = () => new Date(t).toISOString()
  const tick = (minutes: number) => {
    t = Math.min(t + minutes * MINUTE, now - 30_000)
  }

  const items = seed.lines.map(([index, quantity], line) => {
    const product = products[index]
    return {
      id: `1e2f3a4b-5c6d-4e7f-8a9b-${String(n * 100 + line).padStart(12, '0')}`,
      product_id: `2f3a4b5c-6d7e-4f8a-9b0c-${String(index + 1).padStart(12, '0')}`,
      sku: product.sku,
      name: product.name,
      image_url: productImage(product),
      unit_price_paise: product.price,
      quantity,
      line_total_paise: product.price * quantity,
    }
  })
  const subtotal = items.reduce((sum, item) => sum + item.line_total_paise, 0)
  const shipping = seed.freeShipping || subtotal >= FREE_SHIPPING_ABOVE_PAISE ? 0 : SHIPPING_PAISE
  const codFee = seed.method === 'cod' ? COD_FEE_PAISE : 0
  const total = subtotal + shipping + codFee
  const person = contact(seed.contact)

  const order: MockOrder = {
    id: seed.id ?? orderId(n),
    number,
    status: 'draft',
    payment_status: 'unpaid',
    payment_method: null,
    source: seed.source ?? 'bot',
    contact: person,
    total_paise: total,
    item_count: items.reduce((sum, item) => sum + item.quantity, 0),
    created_at: iso(),
    updated_at: iso(),
    conversation_id: conversationId(seed.contact),
    phone_number: {
      id: seedPhoneNumber.id,
      display_phone_number: seedPhoneNumber.display_phone_number,
      verified_name: seedPhoneNumber.verified_name,
    },
    items,
    subtotal_paise: subtotal,
    shipping_paise: shipping,
    cod_fee_paise: codFee,
    currency: 'INR',
    address: null,
    courier_name: '',
    awb_number: '',
    tracking_url: '',
    payment_link: null,
    notes: seed.notes ?? '',
    cancel_reason: '',
    expires_at: new Date(created + CHECKOUT_TTL_MINUTES * MINUTE).toISOString(),
    confirmed_at: null,
    packed_at: null,
    shipped_at: null,
    delivered_at: null,
    cancelled_at: null,
  }

  const events: MockOrderEvent[] = []
  const record: OrderRecord = { workspaceId, order, events }
  const event = (
    type: EventType,
    actor: EventActor,
    detail = '',
    options: { from?: OrderStatus; to?: OrderStatus; user?: string; failedCode?: string } = {},
  ) => {
    // Buyer notifications carry their message and its delivery status.
    const notification = type === 'notification_sent'
    events.push({
      id: `3a4b5c6d-7e8f-4a9b-8c0d-${String(n * 100 + events.length).padStart(12, '0')}`,
      type,
      from_status: options.from ?? '',
      to_status: options.to ?? '',
      actor,
      user: options.user ? userSummary(options.user) : null,
      detail,
      message_id: notification ? `5c6d7e8f-9a0b-4c1d-8e2f-${String(n * 100 + events.length).padStart(12, '0')}` : null,
      message_status: notification ? (options.failedCode ? 'failed' : 'read') : null,
      message_error_code: options.failedCode ?? '',
      created_at: iso(),
    })
  }
  const move = (to: OrderStatus, actor: EventActor, detail = '', user?: string) => {
    event('status_changed', actor, detail, { from: order.status, to, user })
    order.status = to
  }
  const finish = () => {
    order.updated_at = events.at(-1)?.created_at ?? order.created_at
    return record
  }

  event('created', 'buyer', order.source === 'native_cart' ? 'Sent a cart from the WhatsApp catalog.' : 'Checked out from the shop menu.')
  if (seed.status === 'draft') return finish()

  order.status = 'awaiting_confirmation'
  if (seed.priceChanged) {
    tick(1)
    event('price_changed', 'system', `${products[seed.lines[0][0]].name} now costs ${formatPaise(items[0].unit_price_paise)} (was ${formatPaise(items[0].unit_price_paise - 3_000)}). Asked the buyer to confirm.`)
  }
  if (seed.status === 'awaiting_confirmation') return finish()

  order.status = 'awaiting_address'
  if (seed.status === 'awaiting_address') return finish()

  tick(2)
  order.address = address(seed.contact)
  order.status = 'awaiting_payment_method'
  event('address_received', 'buyer', `${order.address.city} ${order.address.pincode}`)
  if (seed.status === 'awaiting_payment_method') return finish()

  order.payment_method = seed.method ?? 'online'
  if (order.payment_method === 'online') {
    tick(1)
    order.status = 'pending_payment'
    const linkCreated = t
    order.payment_link = {
      id: `4b5c6d7e-8f9a-4b0c-8d1e-${String(n).padStart(12, '0')}`,
      short_url: `https://rzp.io/rzp/ss${(1000 + n).toString(36)}q${n}`,
      status: 'created',
      amount_paise: total,
      expires_at: new Date(linkCreated + LINK_EXPIRY_MINUTES * MINUTE).toISOString(),
      paid_at: null,
    }
    event('payment_link_created', 'system', `Sent a ${formatPaise(total)} payment link.`)
    if (seed.status === 'pending_payment') return finish()

    if (seed.status === 'expired' || seed.status === 'needs_attention') {
      tick(LINK_EXPIRY_MINUTES + 2)
      order.payment_link = { ...order.payment_link, status: 'expired' }
      event('payment_link_expired', 'system')
      move('expired', 'system', 'The checkout expired before payment.')
      event('stock_released', 'system', 'Reserved items went back to stock.')
      if (seed.status === 'expired') return finish()
      tick(6)
      order.payment_link = { ...order.payment_link, status: 'paid', paid_at: iso() }
      order.payment_status = 'paid'
      event('payment_received', 'system', `${formatPaise(total)} paid after the checkout expired.`)
      move('needs_attention', 'system', 'Payment arrived after the checkout expired.')
      return finish()
    }

    if (seed.cancelledFrom === 'pending_payment') {
      tick(8)
      order.payment_link = { ...order.payment_link, status: 'cancelled' }
      order.cancel_reason = seed.cancelReason ?? ''
      order.cancelled_at = iso()
      move('cancelled', 'dashboard', order.cancel_reason, ids.demoUser)
      event('stock_released', 'system', 'Reserved items went back to stock.')
      event('notification_sent', 'system', 'Told the buyer the order was cancelled.')
      return finish()
    }

    tick(4)
    order.payment_link = { ...order.payment_link, status: 'paid', paid_at: iso() }
    order.payment_status = 'paid'
    event('payment_received', 'system', `${formatPaise(total)} received.`)
    move('confirmed', 'system')
  } else {
    tick(1)
    order.payment_status = 'cod_pending'
    move('confirmed', 'buyer', 'Chose cash on delivery.')
  }
  order.confirmed_at = iso()
  event('notification_sent', 'system', 'Sent the order confirmation.', { failedCode: seed.confirmationFailedCode })

  const target = seed.status === 'cancelled' ? (seed.cancelledFrom ?? 'confirmed') : seed.status
  const steps: OrderStatus[] = ['packed', 'shipped', 'delivered']
  const reach = steps.slice(0, Math.max(0, steps.indexOf(target) + 1))
  for (const step of reach) {
    if (step === 'packed') {
      tick(180)
      move('packed', 'dashboard', '', ids.demoUser)
      order.packed_at = iso()
      event('notification_sent', 'system', 'Told the buyer the order is packed.')
    } else if (step === 'shipped') {
      tick(18 * 60)
      const [courier, awb, url] = seed.courier ?? ['Delhivery', `DL${48210000 + n}`, '']
      order.courier_name = courier
      order.awb_number = awb
      order.tracking_url = url
      move('shipped', 'seller_whatsapp', `${courier}, AWB ${awb}`)
      order.shipped_at = iso()
      if (seed.notifyShippedFailed) {
        event('notification_failed', 'system', "The buyer's 24-hour window was closed and no template is mapped for shipped orders.")
      } else {
        event('notification_sent', 'system', 'Sent the courier and AWB to the buyer.')
      }
    } else {
      tick(26 * 60)
      move('delivered', 'dashboard', '', ids.priya)
      order.delivered_at = iso()
      event('notification_sent', 'system', 'Told the buyer the order was delivered.')
    }
  }

  if (seed.codCollected && order.payment_method === 'cod') {
    tick(30)
    order.payment_status = 'cod_collected'
    event('cod_collected', 'dashboard', '', { user: ids.arjun })
  }

  if (seed.status === 'cancelled') {
    tick(60)
    order.cancel_reason = seed.cancelReason ?? ''
    order.cancelled_at = iso()
    move('cancelled', 'dashboard', order.cancel_reason, ids.demoUser)
    if (order.payment_status === 'cod_pending') order.payment_status = 'unpaid'
    event('stock_released', 'system', 'Items went back to stock.')
    event('notification_sent', 'system', 'Told the buyer the order was cancelled.')
    if (seed.refunded) {
      tick(90)
      order.payment_status = 'refunded_manual'
      event('refunded_manual', 'dashboard', 'Refunded in the payment gateway.', { user: ids.priya })
    }
  }

  return finish()
}

type Snapshot = { token: unknown; records: OrderRecord[]; counter: number; keys: Map<string, string> }

let snapshot: Snapshot | null = null

function state(): Snapshot {
  if (!snapshot || snapshot.token !== db.refreshTokens) {
    const now = Date.now()
    const keys = new Map<string, string>()
    const records = seeds.map((seed, index) => {
      const record = buildRecord(ids.sharmaSweets, index + 1, seed, now)
      if (seed.key) keys.set(seed.key, record.order.id)
      return record
    })
    // New orders are numbered after the highest seeded number (fixed numbers included).
    const highest = Math.max(...records.map((record) => Number(record.order.number.split('-')[1]) - 1000))
    snapshot = { token: db.refreshTokens, records, counter: Math.max(seeds.length, highest), keys }
  }
  return snapshot
}

/** All order records. `db.refreshTokens` is replaced by `resetMockDb()`, which triggers a rebuild. */
export function orderRecords(): OrderRecord[] {
  return state().records
}

export function findOrder(workspaceId: string, id: string): OrderRecord | undefined {
  return orderRecords().find((record) => record.workspaceId === workspaceId && record.order.id === id)
}

/** A seeded order by its seed key, e.g. `seededOrder('needsAttention')`. */
export function seededOrder(key: string): OrderRecord {
  const id = state().keys.get(key)
  const record = orderRecords().find((candidate) => candidate.order.id === id)
  if (!record) throw new Error(`No seeded order "${key}"`)
  return record
}

export function toOrder(record: OrderRecord): Order {
  return { ...record.order, allowed_transitions: [...orderTransitions[record.order.status]] }
}

export function toListItem({ order }: OrderRecord): Schemas['OrderListItem'] {
  const { id, number, status, payment_status, payment_method, source, contact, total_paise, item_count, created_at, updated_at } = order
  return { id, number, status, payment_status, payment_method, source, contact, total_paise, item_count, created_at, updated_at }
}

/** Appends a timeline event stamped now. */
export function addEvent(
  record: OrderRecord,
  type: EventType,
  actor: EventActor,
  options: { detail?: string; from?: OrderStatus; to?: OrderStatus; userId?: string } = {},
) {
  const at = new Date().toISOString()
  record.events.push({
    id: crypto.randomUUID(),
    type,
    from_status: options.from ?? '',
    to_status: options.to ?? '',
    actor,
    user: options.userId ? userSummary(options.userId) : null,
    detail: options.detail ?? '',
    message_id: null,
    message_status: null,
    message_error_code: '',
    created_at: at,
  })
  record.order.updated_at = at
}

export type ListFilters = {
  status?: string | null
  stage?: string | null
  payment_status?: string | null
  payment_method?: string | null
  contact?: string | null
  search?: string | null
  created_after?: string | null
  created_before?: string | null
}

/** `GET orders/` filtering like the backend: newest first, drafts only when asked for by status. */
export function filterOrders(workspaceId: string, filters: ListFilters): OrderRecord[] {
  const statuses = filters.status ? filters.status.split(',').filter(Boolean) : null
  const stage = filters.stage ? (stageStatuses as Record<string, readonly string[]>)[filters.stage] : null
  const search = filters.search?.trim().toLowerCase() ?? ''
  const digits = search.replace(/\D/g, '')
  const after = filters.created_after ? Date.parse(filters.created_after) : null
  const before = filters.created_before ? Date.parse(filters.created_before) : null

  return orderRecords()
    .filter(({ workspaceId: ws, order }) => {
      if (ws !== workspaceId) return false
      if (statuses ? !statuses.includes(order.status) : order.status === 'draft') return false
      if (stage && !stage.includes(order.status)) return false
      if (filters.payment_status && order.payment_status !== filters.payment_status) return false
      if (filters.payment_method && order.payment_method !== filters.payment_method) return false
      if (filters.contact && order.contact.id !== filters.contact) return false
      const created = Date.parse(order.created_at)
      if (after !== null && !Number.isNaN(after) && created < after) return false
      if (before !== null && !Number.isNaN(before) && created >= before) return false
      if (search) {
        const matches =
          order.number.toLowerCase().includes(search) ||
          order.contact.name.toLowerCase().includes(search) ||
          (digits.length >= 3 && order.contact.phone_e164.includes(digits))
        if (!matches) return false
      }
      return true
    })
    .sort((a, b) => b.order.created_at.localeCompare(a.order.created_at))
}

/** `GET orders/summary/`: "today" is in the workspace time zone. */
export function orderSummary(workspaceId: string, now = Date.now()): Schemas['OrderSummary'] {
  const timeZone = db.workspaces.find((workspace) => workspace.id === workspaceId)?.time_zone || 'Asia/Kolkata'
  const today = formatInZone(new Date(now).toISOString(), timeZone, 'yyyy-MM-dd')
  const orders = orderRecords()
    .filter((record) => record.workspaceId === workspaceId)
    .map((record) => record.order)
  const confirmedOrLater = ['confirmed', 'packed', 'shipped', 'delivered', 'needs_attention']
  const todays = orders.filter(
    (order) => confirmedOrLater.includes(order.status) && formatInZone(order.created_at, timeZone, 'yyyy-MM-dd') === today,
  )
  return {
    today_count: todays.length,
    today_revenue_paise: todays.reduce((sum, order) => sum + order.total_paise, 0),
    open_count: orders.filter((order) => (stageStatuses.open as readonly string[]).includes(order.status)).length,
    needs_attention_count: orders.filter((order) => order.status === 'needs_attention').length,
    awaiting_payment_count: orders.filter((order) => order.status === 'pending_payment').length,
  }
}

/** A new confirmed order placed just now, as the demo emitter and realtime tests use. */
export function createMockOrder(workspaceId: string = ids.sharmaSweets): OrderRecord {
  const snap = state()
  snap.counter += 1
  const n = snap.counter
  const k = n % 7
  // Placed 15 minutes ago so its checkout steps fit before "now".
  const seed: Seed = {
    hoursAgo: 0.25,
    contact: 30 + (n % 18),
    lines: [
      [n % products.length, 1 + (k % 2)],
      ...(k % 3 === 0 ? [] : ([[(n + 4) % products.length, 1]] as [number, number][])),
    ],
    status: 'confirmed',
    method: k % 2 ? 'online' : 'cod',
    source: k % 3 === 1 ? 'native_cart' : 'bot',
  }
  const record = buildRecord(workspaceId, n, seed, Date.now())
  snap.records.push(record)
  return record
}
