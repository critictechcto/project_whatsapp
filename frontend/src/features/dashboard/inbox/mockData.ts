/**
 * In-memory inbox data for mock mode and tests: Sharma Sweets conversations in Hindi and English.
 * Times are relative to when the state is first used, so service windows are live (open, closing
 * soon, closed). State is tied to the mock db and resets with `resetMockDb()`.
 */
import type { MessageTemplate } from '../../../api/types'
import { findComponent, fillVariables } from '../../../components/app/whatsapp/template'
import { db, type Mutable } from '../../../mocks/db'
import { ids, indianMobile, indianName, seedPhoneNumber, seedTemplates } from '../../../mocks/seed'
import { apiUrl } from '../../../mocks/utils'
import type { Conversation, ConversationNote, MediaAsset, Message, MessageStatus, MessageType, UserSummary } from './api'

const MINUTE = 60_000
const HOUR = 60 * MINUTE
const DAY = 24 * HOUR

export type MockMessage = Mutable<Message>

export type MockConversation = {
  id: string
  workspace_id: string
  contact: Mutable<Conversation['contact']>
  phone_number: Conversation['phone_number']
  status: Conversation['status']
  assignee_id: string | null
  unread_count: number
  last_inbound_at: string | null
  created_at: string
  updated_at: string
}

export type InboxMockState = {
  conversations: MockConversation[]
  /** Conversation id → messages, oldest first. */
  messages: Map<string, MockMessage[]>
  notes: Map<string, ConversationNote[]>
  uploads: Map<string, { asset: MediaAsset; blob: Blob; workspaceId: string }>
  /** Uploaded files attached to sent messages. */
  messageBlobs: Map<string, Blob>
  /** `${workspaceId}:${Idempotency-Key}` → message id. */
  idempotency: Map<string, string>
  sends: number
}

function conversationId(n: number) {
  return `c3d4e5f6-a7b8-4c9d-8e0f-${String(n).padStart(12, '0')}`
}

export const inboxMockIds = {
  wholesaleNumber: '7e3a9b1c-5d2f-4a8e-b6c0-9f1e3d5a7b23',
  /** Open, assigned to Rohan, 2 unread, long history. */
  ananya: conversationId(1),
  /** Open, unassigned, location and a quoted reply. */
  vihaan: conversationId(2),
  /** Window closes in about 30 minutes; a document and a failed message. */
  ishita: conversationId(3),
  /** Contact opted out: sends return 409 `contact_opted_out`. */
  aditya: conversationId(4),
  /** Window closed three days ago: free-form sends return 409 `outside_service_window`. */
  meera: conversationId(5),
  /** Pending: video, sticker, reaction and an unsupported message. */
  reyansh: conversationId(6),
  /** Closed conversation. */
  arnav: conversationId(7),
  /** On the unregistered wholesale number: sends return 409 `phone_number_not_registered`. */
  kavya: conversationId(8),
  /** Assigned to Rohan: template, button reply and a contact card. */
  vivaan: conversationId(9),
  /** Shop bot flow: menu, product card, native cart, address, payment link, confirmation. */
  kabir: conversationId(10),
  /** The native cart `order` message in Kabir's thread. */
  kabirCart: 'd7e8f9a0-1b2c-4d3e-9f4a-0000000c0a01',
  /** The bot's product card in Kabir's thread. */
  kabirProductCard: 'd7e8f9a0-1b2c-4d3e-9f4a-0000000c0a02',
  /** The bot's order confirmation to Kabir; Meta rejected it with a payment method error. */
  kabirConfirmation: 'd7e8f9a0-1b2c-4d3e-9f4a-0000000c0a03',
  /** Kabir's order SS-1042 (seeded with the same id in the orders mock). */
  kabirOrder: '7d0a4e3c-9f6b-4a1c-a5e8-3b4c5d6e7f01',
  /** Delivered outbound message in Ananya's thread. */
  ananyaDelivered: 'd7e8f9a0-1b2c-4d3e-9f4a-00000000a001',
} as const

export const mainNumber: Conversation['phone_number'] = {
  id: seedPhoneNumber.id,
  display_phone_number: seedPhoneNumber.display_phone_number,
  verified_name: seedPhoneNumber.verified_name,
}

export const wholesaleNumber: Conversation['phone_number'] = {
  id: inboxMockIds.wholesaleNumber,
  display_phone_number: '+91 98290 44556',
  verified_name: 'Sharma Sweets Wholesale',
}

/** Numbers whose registration isn't complete, so sending fails. */
export const unregisteredNumbers = new Set<string>([wholesaleNumber.id])

/* ---------- Contacts (same ids and consent as the shared contacts fallback) ---------- */

const CONTACT_PREFIX = 'e0f1a2b3-c4d5-4e6f-8a9b-'

export function contactStatus(i: number): Conversation['contact']['marketing_opt_in_status'] {
  return i % 9 === 4 ? 'opted_out' : i % 3 === 0 ? 'unknown' : 'opted_in'
}

export function seedContact(i: number): Conversation['contact'] {
  return {
    id: `${CONTACT_PREFIX}${String(i + 1).padStart(12, '0')}`,
    name: indianName(i),
    phone_e164: indianMobile(i),
    marketing_opt_in_status: contactStatus(i),
  }
}

export function contactIndexFromId(id: string): number | null {
  if (!id.startsWith(CONTACT_PREFIX)) return null
  const index = Number(id.slice(CONTACT_PREFIX.length)) - 1
  return Number.isInteger(index) && index >= 0 && index < 48 ? index : null
}

export function userSummary(userId: string | null | undefined): UserSummary | null {
  const user = db.users.find((candidate) => candidate.id === userId)
  return user ? { id: user.id, full_name: user.full_name ?? '', email: user.email } : null
}

export function templateBody(templateId: string, params: readonly string[] = []): { template: (typeof seedTemplates)[number]; text: string } | null {
  const template = seedTemplates.find((candidate) => candidate.id === templateId)
  if (!template) return null
  const body = findComponent({ components: template.components as unknown as MessageTemplate['components'] }, 'BODY')
  return { template, text: body?.text ? fillVariables(body.text, params) : '' }
}

/* ---------- Message builders ---------- */

type MessageSpec = {
  dir: 'in' | 'out'
  /** Milliseconds before the state's reference time. */
  ago: number
  text?: string
  type?: MessageType
  status?: MessageStatus
  source?: Message['source']
  by?: string | null
  media?: { mime_type: string; file_name: string; size: number; available?: boolean }
  template?: string
  replyTo?: string
  error?: [code: string, message: string]
  id?: string
  /** Raw Cloud API `interactive` object of an outbound interactive message. */
  interactive?: Record<string, unknown>
  /** Cart of an inbound native catalog `order` message. */
  order?: Message['order']
  /** What an inbound button, list or form reply chose. */
  reply?: Message['reply']
  /** The order the message belongs to (the same id exists in the orders mock). */
  orderId?: string
}

export function mediaUrl(messageId: string) {
  return apiUrl(`/api/v1/inbox/messages/${messageId}/media/`)
}

export function wamidFor(messageId: string) {
  return `wamid.HBgM${messageId.replace(/-/g, '').slice(0, 24).toUpperCase()}`
}

/** Timestamps that match a status (sent → delivered → read, or failed). */
export function statusTimes(status: MessageStatus, createdMs: number) {
  const reached = (target: MessageStatus[]) => target.includes(status)
  return {
    sent_at: reached(['sent', 'delivered', 'read']) ? new Date(createdMs + 2_000).toISOString() : null,
    delivered_at: reached(['delivered', 'read']) ? new Date(createdMs + 5_000).toISOString() : null,
    read_at: reached(['read']) ? new Date(createdMs + 60_000).toISOString() : null,
    failed_at: reached(['failed']) ? new Date(createdMs + 3_000).toISOString() : null,
  }
}

const inboundPool = [
  'Namaste, kya aaj delivery ho sakti hai?',
  'Motichoor laddoo ka 1 kg ka rate kya hai?',
  'Is the Diwali gift box available in 2 kg?',
  'Payment kar diya hai, please confirm karein.',
  'Can I pick up the order from the MI Road shop?',
  'Sugar-free options hain kya?',
  'Order 4521 ka status kya hai?',
  'Thank you, mithai bahut acchi thi!',
  'Kal subah 10 baje tak mil jayega?',
  'Please share the menu for the wedding order.',
  'Do you deliver to Malviya Nagar?',
  'Rasgulla tin available hai?',
]

const outboundPool = [
  'Namaste! Haan ji, aaj shaam 6 baje tak delivery ho jayegi.',
  'Motichoor laddoo ₹560 per kg hai.',
  'Yes, the 2 kg Diwali box is ₹1,450. Shall I book one for you?',
  'Payment mil gaya, dhanyavaad! Aapka order confirm hai.',
  'Sure, it will be ready for pickup after 4 PM.',
  'Haan ji, sugar-free kaju katli aur anjeer barfi available hain.',
  'Aapka order dispatch ho gaya hai.',
  'Aapka bahut dhanyavaad! Phir se order kijiye.',
  'Ji, kal subah 9:30 tak pahunch jayega.',
  'Menu PDF abhi bhej rahe hain.',
  'Yes, we deliver across Jaipur within 3 hours.',
  'Haan ji, 1 kg tin ₹380 ka hai.',
]

/** Customer replies used by the mock after a send. */
export const replyPool = [
  'Theek hai, thank you!',
  'Great, please go ahead.',
  'Kitne baje tak aayega?',
  'Ok ji, dhanyavaad.',
  'Can you add one more box?',
]

function build(): InboxMockState {
  const now = Date.now()
  const state: InboxMockState = {
    conversations: [],
    messages: new Map(),
    notes: new Map(),
    uploads: new Map(),
    messageBlobs: new Map(),
    idempotency: new Map(),
    sends: 0,
  }
  let seq = 0
  const iso = (ago: number) => new Date(now - ago).toISOString()

  const message = (conversation: string, spec: MessageSpec): MockMessage => {
    const id = spec.id ?? `d7e8f9a0-1b2c-4d3e-8f4a-${String(++seq).padStart(12, '0')}`
    const createdMs = now - spec.ago
    const inbound = spec.dir === 'in'
    const status: MessageStatus = inbound ? 'received' : (spec.status ?? 'read')
    const source: Message['source'] = inbound ? 'inbound' : (spec.source ?? 'inbox')
    const template = spec.template ? seedTemplates.find((candidate) => candidate.id === spec.template) : undefined
    return {
      id,
      conversation_id: conversation,
      direction: inbound ? 'inbound' : 'outbound',
      type: spec.type ?? (template ? 'template' : 'text'),
      text: spec.text ?? '',
      status,
      source,
      error_code: spec.error?.[0] ?? '',
      error_message: spec.error?.[1] ?? '',
      template: template ? { id: template.id, name: template.name, language: template.language } : null,
      interactive: spec.interactive ?? null,
      order: spec.order ?? null,
      reply: inbound ? (spec.reply ?? null) : null,
      order_id: spec.orderId ?? null,
      media: spec.media
        ? {
            mime_type: spec.media.mime_type,
            file_name: spec.media.file_name,
            size: spec.media.size,
            download_url: spec.media.available === false ? null : mediaUrl(id),
          }
        : null,
      reply_to_message_id: spec.replyTo ?? null,
      sent_by: inbound || source !== 'inbox' ? null : userSummary(spec.by === undefined ? ids.demoUser : spec.by),
      wamid: wamidFor(id),
      created_at: new Date(createdMs).toISOString(),
      ...(inbound ? { sent_at: null, delivered_at: null, read_at: null, failed_at: null } : statusTimes(status, createdMs)),
    }
  }

  const add = (
    n: number,
    options: {
      contact: number | Conversation['contact']
      status?: Conversation['status']
      assignee?: string | null
      unread?: number
      number?: Conversation['phone_number']
    },
    specs: MessageSpec[],
    notes: { by: string; ago: number; body: string }[] = [],
  ) => {
    const id = conversationId(n)
    const messages = specs.map((spec) => message(id, spec)).sort((a, b) => a.created_at.localeCompare(b.created_at))
    const lastInbound = [...messages].reverse().find((candidate) => candidate.direction === 'inbound')
    const first = messages[0]
    state.conversations.push({
      id,
      workspace_id: ids.sharmaSweets,
      contact: typeof options.contact === 'number' ? seedContact(options.contact) : options.contact,
      phone_number: options.number ?? mainNumber,
      status: options.status ?? 'open',
      assignee_id: options.assignee ?? null,
      unread_count: options.unread ?? 0,
      last_inbound_at: lastInbound?.created_at ?? null,
      created_at: first ? first.created_at : iso(DAY),
      updated_at: messages.at(-1)?.created_at ?? iso(DAY),
    })
    state.messages.set(id, messages)
    state.notes.set(
      id,
      notes.map((note, index) => ({
        id: `f1a2b3c4-d5e6-4f70-8a9b-${String(n * 100 + index).padStart(12, '0')}`,
        body: note.body,
        author: userSummary(note.by)!,
        created_at: iso(note.ago),
      })),
    )
  }

  // A: Ananya, long history for pagination.
  const history: MessageSpec[] = Array.from({ length: 40 }, (_, k) => ({
    dir: k % 2 === 0 ? 'in' : 'out',
    ago: 6 * DAY - k * 2.9 * HOUR,
    text: k % 2 === 0 ? inboundPool[k % inboundPool.length] : outboundPool[(k - 1) % outboundPool.length],
    by: k % 4 === 1 ? ids.priya : ids.demoUser,
  }))
  add(
    1,
    { contact: 1, assignee: ids.demoUser, unread: 2 },
    [
      ...history,
      {
        dir: 'in',
        ago: 26 * HOUR,
        type: 'image',
        text: 'Ye wala box chahiye, 2 kg',
        media: { mime_type: 'image/jpeg', file_name: 'IMG-20260913-WA0012.jpg', size: 184_320 },
      },
      { dir: 'out', ago: 25.5 * HOUR, text: 'Ji bilkul, 2 kg Diwali gift box ₹1,450 ka hai. Order book kar dun?' },
      { dir: 'in', ago: 40 * MINUTE, text: 'Haan, kar dijiye. Delivery kab tak hogi?' },
      { dir: 'out', ago: 25 * MINUTE, text: 'Haan ji, kal shaam tak delivery ho jayegi', status: 'delivered', id: inboxMockIds.ananyaDelivered },
      { dir: 'in', ago: 20 * MINUTE, text: 'Thank you! Kaju katli 1 kg bhi add kar dijiye' },
      { dir: 'in', ago: 19 * MINUTE, text: 'Aur ek box soan papdi bhi' },
    ],
    [{ by: ids.priya, ago: 30 * MINUTE, body: 'Regular customer. Diwali order par 10% discount de sakte hain.' }],
  )

  // B: Vihaan, unassigned, location and a quoted reply.
  const vihaanQuestion = 'd7e8f9a0-1b2c-4d3e-9f4a-00000000b001'
  add(2, { contact: 2, unread: 1 }, [
    { dir: 'in', ago: 5.5 * HOUR, text: 'Hello, is your shop open on Sunday?', id: vihaanQuestion },
    { dir: 'out', ago: 5.4 * HOUR, text: 'Yes, we are open 9 AM to 10 PM on Sundays.', replyTo: vihaanQuestion, by: ids.arjun },
    { dir: 'in', ago: 5 * HOUR, type: 'location', text: 'Near Raja Park, Jaipur 302004' },
    { dir: 'in', ago: 4.9 * HOUR, text: 'Can you deliver here?' },
  ])

  // C: Ishita, window closes in about 30 minutes.
  add(
    3,
    { contact: 5, assignee: ids.priya },
    [
      { dir: 'in', ago: 23.5 * HOUR, text: 'Please send your wholesale price list' },
      {
        dir: 'out',
        ago: 23.4 * HOUR,
        type: 'document',
        text: 'Ye rahi hamari price list',
        by: ids.priya,
        media: { mime_type: 'application/pdf', file_name: 'Sharma-Sweets-Price-List-2026.pdf', size: 248_000 },
      },
      {
        dir: 'out',
        ago: 23.3 * HOUR,
        text: 'Koi aur jaankari chahiye to bataiye',
        by: ids.priya,
        status: 'failed',
        error: ['131026', 'Message undeliverable. The recipient may be unable to receive messages right now.'],
      },
    ],
    [{ by: ids.demoUser, ago: 23 * HOUR, body: 'Wholesale enquiry. Follow up after the Diwali stock arrives.' }],
  )

  // D: Aditya, opted out.
  const diwali = templateBody(seedTemplates[1].id, ['Aditya', '20 Oct'])
  add(4, { contact: 4, unread: 1 }, [
    { dir: 'out', ago: 3 * HOUR, template: seedTemplates[1].id, text: diwali?.text, source: 'campaign' },
    { dir: 'in', ago: 2 * HOUR, text: 'STOP' },
  ])

  // E: Meera, window closed three days ago.
  add(5, { contact: 7, assignee: ids.arjun }, [
    { dir: 'in', ago: 3 * DAY + 2 * HOUR, type: 'audio', media: { mime_type: 'audio/ogg', file_name: 'voice-note.ogg', size: 38_000 } },
    { dir: 'out', ago: 3 * DAY, text: 'Ji, aapka order kal tak pahunch jayega.', by: ids.arjun },
  ])

  // F: Reyansh, pending with rich message types.
  const reyanshReply = 'd7e8f9a0-1b2c-4d3e-9f4a-00000000f001'
  add(6, { contact: 8, status: 'pending', assignee: ids.demoUser }, [
    {
      dir: 'in',
      ago: 15 * HOUR,
      type: 'video',
      text: 'Packaging damaged tha',
      media: { mime_type: 'video/mp4', file_name: 'VID-20260913.mp4', size: 2_400_000, available: false },
    },
    { dir: 'out', ago: 14.8 * HOUR, text: 'Sorry for the trouble! Hum replacement bhej rahe hain.', id: reyanshReply },
    { dir: 'in', ago: 14.5 * HOUR, type: 'sticker', media: { mime_type: 'image/webp', file_name: 'sticker.webp', size: 18_000 } },
    { dir: 'in', ago: 14.2 * HOUR, type: 'reaction', text: '👍', replyTo: reyanshReply },
    { dir: 'in', ago: 14 * HOUR, type: 'unsupported' },
  ])

  // G: Arnav, closed.
  add(7, { contact: 10, status: 'closed', assignee: ids.priya }, [
    { dir: 'in', ago: 6 * DAY, text: 'Order mil gaya, thank you' },
    { dir: 'out', ago: 5.9 * DAY, text: 'Dhanyavaad! Phir se seva ka mauka dijiye.', by: ids.priya },
  ])

  // H: Kavya, on the unregistered wholesale number.
  add(8, { contact: 11, unread: 3, number: wholesaleNumber }, [
    { dir: 'in', ago: 1.2 * HOUR, text: 'Hi, 50 kg besan laddoo ka wholesale rate?' },
    { dir: 'in', ago: 1.1 * HOUR, text: 'Delivery Ajmer tak ho jayegi?' },
    { dir: 'in', ago: 1 * HOUR, text: 'Please call back' },
  ])

  // I: Vivaan, automation template, button reply and a contact card.
  const shipped = templateBody(seedTemplates[0].id, ['Vivaan', '1 kg Kaju Katli', '14 Sep'])
  add(9, { contact: 12, assignee: ids.demoUser }, [
    { dir: 'out', ago: 7 * HOUR, template: seedTemplates[0].id, text: shipped?.text, source: 'automation' },
    { dir: 'in', ago: 6.5 * HOUR, type: 'button', text: 'Talk to us', reply: { kind: 'button', id: 'Talk to us', title: 'Talk to us', description: '' } },
    { dir: 'in', ago: 6.4 * HOUR, type: 'contacts', text: 'Suresh Rao, +91 98765 43210' },
    { dir: 'out', ago: 6 * HOUR, text: 'Ji Vivaan, Suresh ji ko bhi call kar lenge.', status: 'delivered' },
  ])

  // J: Kabir, a shop bot flow from "hi" to a paid order (bot replies are commerce sends).
  const bot = { dir: 'out', source: 'commerce', status: 'read' } as const
  const orderBot = { ...bot, orderId: inboxMockIds.kabirOrder }
  const shopEnd = 55 * MINUTE
  add(10, { contact: 6 }, [
    { dir: 'in', ago: shopEnd + 14 * MINUTE, text: 'hi' },
    {
      ...bot,
      ago: shopEnd + 13.9 * MINUTE,
      type: 'interactive',
      text: 'Namaste! Welcome to Sharma Sweets. Fresh mithai and namkeen, delivered across Jaipur.',
      interactive: {
        type: 'list',
        header: { type: 'text', text: 'Sharma Sweets' },
        body: { text: 'Namaste! Welcome to Sharma Sweets. Fresh mithai and namkeen, delivered across Jaipur.' },
        footer: { text: 'Powered by UpChatz' },
        action: {
          button: 'View menu',
          sections: [
            {
              title: 'Shop',
              rows: [
                { id: 'upc:shop:col:5b8e2c1a-7d4f-4e9a-b3c6-1f2a3b4c5d01:0', title: 'Mithai', description: 'Kaju katli, laddoo, barfi' },
                { id: 'upc:shop:col:5b8e2c1a-7d4f-4e9a-b3c6-1f2a3b4c5d02:0', title: 'Namkeen', description: 'Bhujia, mathri, mixture' },
                { id: 'upc:shop:col:5b8e2c1a-7d4f-4e9a-b3c6-1f2a3b4c5d03:0', title: 'Gift boxes', description: 'Festive assortments' },
              ],
            },
            {
              title: 'Help',
              rows: [
                { id: 'upc:shop:orders', title: 'My orders' },
                { id: 'upc:shop:talk', title: 'Talk to us' },
              ],
            },
          ],
        },
      },
    },
    {
      dir: 'in',
      ago: shopEnd + 13 * MINUTE,
      type: 'interactive',
      text: 'Mithai',
      reply: { kind: 'list', id: 'upc:shop:col:5b8e2c1a-7d4f-4e9a-b3c6-1f2a3b4c5d01:0', title: 'Mithai', description: 'Kaju katli, laddoo, barfi' },
    },
    {
      ...bot,
      id: inboxMockIds.kabirProductCard,
      ago: shopEnd + 12.9 * MINUTE,
      type: 'interactive',
      text: 'Kaju Katli 250 g · ₹220',
      interactive: {
        type: 'button',
        header: { type: 'text', text: 'Kaju Katli 250 g' },
        body: { text: '₹220\nPure ghee kaju katli, made fresh every morning.' },
        footer: { text: '1 of 6 in Mithai' },
        action: {
          buttons: [
            { type: 'reply', reply: { id: 'upc:shop:add:6c9f3d2b-8e5a-4f0b-94d7-2a3b4c5d6e01:1', title: 'Add to cart' } },
            { type: 'reply', reply: { id: 'upc:shop:col:5b8e2c1a-7d4f-4e9a-b3c6-1f2a3b4c5d01:1', title: 'Next item' } },
            { type: 'reply', reply: { id: 'upc:shop:menu', title: 'Menu' } },
          ],
        },
      },
    },
    {
      dir: 'in',
      ago: shopEnd + 12 * MINUTE,
      type: 'interactive',
      text: 'Add to cart',
      reply: { kind: 'button', id: 'upc:shop:add:6c9f3d2b-8e5a-4f0b-94d7-2a3b4c5d6e01:1', title: 'Add to cart', description: '' },
    },
    {
      dir: 'in',
      id: inboxMockIds.kabirCart,
      ago: shopEnd + 9 * MINUTE,
      type: 'order',
      text: 'Cart: 3 items, ₹540.00',
      orderId: inboxMockIds.kabirOrder,
      order: {
        catalog_id: '1234567890123456',
        items: [
          { product_retailer_id: 'SS-KAJU-250', name: 'Kaju Katli 250 g', quantity: 2, item_price: 220, currency: 'INR' },
          // No workspace product has this SKU any more, so the cart shows the SKU.
          { product_retailer_id: 'SS-SOAN-250', name: null, quantity: 1, item_price: 100, currency: 'INR' },
        ],
      },
    },
    {
      ...orderBot,
      ago: shopEnd + 8.9 * MINUTE,
      type: 'interactive',
      text: 'Where should we deliver order SS-1042? Tap below to share your address.',
      interactive: {
        type: 'address_message',
        body: { text: 'Where should we deliver order SS-1042? Tap below to share your address.' },
        action: { name: 'address_message', parameters: { country: 'IN' } },
      },
    },
    {
      dir: 'in',
      ago: shopEnd + 6 * MINUTE,
      type: 'interactive',
      text: 'Address shared',
      reply: { kind: 'nfm', id: 'address_message', title: 'Address shared', description: '' },
    },
    {
      ...orderBot,
      ago: shopEnd + 5.9 * MINUTE,
      type: 'interactive',
      text: 'Delivering to C-12, Malviya Nagar, Jaipur 302017. How would you like to pay ₹540?',
      interactive: {
        type: 'button',
        body: { text: 'Delivering to C-12, Malviya Nagar, Jaipur 302017. How would you like to pay ₹540?' },
        action: {
          buttons: [
            { type: 'reply', reply: { id: 'upc:chk:pay:7d0a4e3c-9f6b-4a1c-a5e8-3b4c5d6e7f01:online', title: 'Pay online' } },
            { type: 'reply', reply: { id: 'upc:chk:pay:7d0a4e3c-9f6b-4a1c-a5e8-3b4c5d6e7f01:cod', title: 'Cash on delivery' } },
          ],
        },
      },
    },
    {
      dir: 'in',
      ago: shopEnd + 5 * MINUTE,
      type: 'interactive',
      text: 'Pay online',
      orderId: inboxMockIds.kabirOrder,
      reply: { kind: 'button', id: 'upc:chk:pay:7d0a4e3c-9f6b-4a1c-a5e8-3b4c5d6e7f01:online', title: 'Pay online', description: '' },
    },
    {
      ...orderBot,
      ago: shopEnd + 4.9 * MINUTE,
      type: 'interactive',
      text: 'Order SS-1042 · ₹540. Pay by UPI or card. This link expires in 30 minutes.',
      interactive: {
        type: 'cta_url',
        body: { text: 'Order SS-1042 · ₹540\nPay by UPI or card. This link expires in 30 minutes.' },
        footer: { text: 'Payment goes to Sharma Sweets via Razorpay' },
        action: { name: 'cta_url', parameters: { display_text: 'Pay ₹540', url: 'https://rzp.io/rzp/demo-SS1042' } },
      },
    },
    {
      ...orderBot,
      id: inboxMockIds.kabirConfirmation,
      ago: shopEnd,
      status: 'failed',
      error: ['131042', 'Business eligibility payment issue'],
      type: 'interactive',
      text: 'Payment received, thank you! Order SS-1042 is confirmed. We will message you when it ships.',
      interactive: {
        type: 'button',
        body: { text: 'Payment received, thank you! Order SS-1042 is confirmed. We will message you when it ships.' },
        action: {
          buttons: [
            { type: 'reply', reply: { id: 'upc:ord:view:7d0a4e3c-9f6b-4a1c-a5e8-3b4c5d6e7f01', title: 'View order' } },
            { type: 'reply', reply: { id: 'upc:shop:menu', title: 'Shop more' } },
          ],
        },
      },
    },
  ])

  // Generated conversations to fill the list (more than one page of open conversations).
  const assignees = [null, ids.demoUser, ids.priya, ids.arjun]
  for (let k = 0; k < 24; k++) {
    const base = 8 * HOUR + k * 3.3 * HOUR
    const endsInbound = k % 2 === 0
    const specs: MessageSpec[] = [
      { dir: 'in', ago: base + 20 * MINUTE, text: inboundPool[k % inboundPool.length] },
      {
        dir: 'out',
        ago: base + 10 * MINUTE,
        text: outboundPool[k % outboundPool.length],
        status: k % 7 === 3 ? 'delivered' : 'read',
        by: assignees[k % 4] ?? ids.demoUser,
      },
    ]
    if (endsInbound) specs.push({ dir: 'in', ago: base, text: inboundPool[(k + 5) % inboundPool.length] })
    add(
      20 + k,
      {
        contact: 14 + k,
        status: k % 6 === 5 ? 'closed' : k % 6 === 2 ? 'pending' : 'open',
        assignee: assignees[k % 4],
        unread: endsInbound && k % 4 === 0 ? 1 + (k % 3) : 0,
      },
      specs,
    )
  }

  return state
}

const states = new WeakMap<object, InboxMockState>()

/** The inbox mock state for the current mock db (rebuilt after `resetMockDb()`). */
export function inboxState(): InboxMockState {
  let state = states.get(db.refreshTokens)
  if (!state) {
    state = build()
    states.set(db.refreshTokens, state)
  }
  return state
}

export function toConversation(state: InboxMockState, conversation: MockConversation): Conversation {
  const last = state.messages.get(conversation.id)?.at(-1)
  const expires = conversation.last_inbound_at ? new Date(Date.parse(conversation.last_inbound_at) + DAY).toISOString() : null
  return {
    id: conversation.id,
    contact: { ...conversation.contact },
    phone_number: conversation.phone_number,
    status: conversation.status,
    assignee: userSummary(conversation.assignee_id),
    unread_count: conversation.unread_count,
    last_message_at: last?.created_at ?? null,
    last_inbound_at: conversation.last_inbound_at,
    service_window_expires_at: expires,
    window_open: expires ? Date.parse(expires) > Date.now() : false,
    last_message: last ? { direction: last.direction, type: last.type, text: last.text, status: last.status, created_at: last.created_at } : null,
    created_at: conversation.created_at,
    updated_at: conversation.updated_at,
  }
}

/* ---------- Media placeholders ---------- */

export function placeholderImage(label: string): Blob {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="480" height="360" viewBox="0 0 480 360"><rect width="480" height="360" fill="#efe4cf"/><circle cx="240" cy="160" r="70" fill="#d9a441"/><rect x="150" y="120" width="180" height="90" rx="10" fill="#b5482a"/><rect x="232" y="120" width="16" height="90" fill="#f3d27a"/><text x="240" y="290" font-family="sans-serif" font-size="20" text-anchor="middle" fill="#5b4a33">${label.replace(/[<&>]/g, '')}</text></svg>`
  return new Blob([svg], { type: 'image/svg+xml' })
}

/** One second of a soft two-note tone as 8 kHz mono WAV. */
export function placeholderAudio(): Blob {
  const rate = 8000
  const samples = rate
  const buffer = new ArrayBuffer(44 + samples)
  const view = new DataView(buffer)
  const write = (offset: number, text: string) => [...text].forEach((char, i) => view.setUint8(offset + i, char.charCodeAt(0)))
  write(0, 'RIFF')
  view.setUint32(4, 36 + samples, true)
  write(8, 'WAVE')
  write(12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, 1, true)
  view.setUint32(24, rate, true)
  view.setUint32(28, rate, true)
  view.setUint16(32, 1, true)
  view.setUint16(34, 8, true)
  write(36, 'data')
  view.setUint32(40, samples, true)
  for (let i = 0; i < samples; i++) {
    const frequency = i < samples / 2 ? 440 : 554
    const envelope = Math.sin((Math.PI * (i % (samples / 2))) / (samples / 2))
    view.setUint8(44 + i, 128 + Math.round(40 * envelope * Math.sin((2 * Math.PI * frequency * i) / rate)))
  }
  return new Blob([buffer], { type: 'audio/wav' })
}

export function placeholderDocument(fileName: string): Blob {
  const text = `Sharma Sweets - ${fileName.replace(/[()\\]/g, '')} (demo file)`
  const pdf = `%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 420 200] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj
4 0 obj << /Length ${text.length + 40} >> stream
BT /F1 14 Tf 24 100 Td (${text}) Tj ET
endstream endobj
5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj
trailer << /Root 1 0 R >>
%%EOF`
  return new Blob([pdf], { type: 'application/pdf' })
}
