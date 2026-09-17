/**
 * In-memory data for the contacts mock handlers (mock mode and tests). Rebuilt whenever the shared
 * mock database is reset (`resetMockDb` swaps `db.generation` for a new object), so every test
 * starts from the same seed.
 */
import type { Schemas } from '../../../api/types'
import { db, type Mutable } from '../../../mocks/db'
import { daysAgo, ids, indianCities, indianMobile, indianName, seedTags } from '../../../mocks/seed'

export type MockTag = Mutable<Schemas['Tag']> & { workspace_id: string }
export type MockContact = Mutable<Schemas['Contact']> & { workspace_id: string; tags: string[] }
export type MockConsentEvent = Mutable<Schemas['ConsentEvent']> & { workspace_id: string; contact_id: string }
export type MockImport = Mutable<Schemas['ContactImport']> & {
  workspace_id: string
  errors: Schemas['ImportRowError'][]
  tags: string[]
  /** GETs seen so far; the job advances one step per poll. */
  polls: number
  /** Rows parsed from the uploaded file, applied when the job completes. */
  rows: Array<{ line: number; cells: string[] }>
  header: string[]
}
export type MockConversation = Mutable<Schemas['Conversation']> & { workspace_id: string }

export type ContactsMockState = {
  tags: MockTag[]
  contacts: MockContact[]
  consentEvents: MockConsentEvent[]
  imports: MockImport[]
  conversations: MockConversation[]
}

const pad = (n: number) => String(n).padStart(12, '0')

/** Same ids as the shared read-only fallback in `mocks/handlers/shared.ts`. */
export const contactId = (i: number) => `e0f1a2b3-c4d5-4e6f-8a9b-${pad(i + 1)}`
const kaveriContactId = (i: number) => `e0f1a2b3-c4d5-4e6f-8a9c-${pad(i + 1)}`
const eventId = (n: number) => `f1e2d3c4-b5a6-4978-8a6b-${pad(n)}`
const conversationId = (i: number) => `d7c6b5a4-9382-4716-a5b4-${pad(i + 1)}`

export const mockTagIds = {
  regular: seedTags[0].id,
  diwali: seedTags[1].id,
  wholesale: seedTags[2].id,
  vip: 'c1d2e3f4-a5b6-4c7d-8e9f-0a1b2c3d4e64',
  mumbai: 'c1d2e3f4-a5b6-4c7d-8e9f-0a1b2c3d4e65',
  bengaluru: 'c1d2e3f4-a5b6-4c7d-8e9f-0a1b2c3d4e66',
  jaipur: 'c1d2e3f4-a5b6-4c7d-8e9f-0a1b2c3d4e67',
  corporate: 'c1d2e3f4-a5b6-4c7d-8e9f-0a1b2c3d4e68',
} as const

const hoursAgo = (hours: number) => daysAgo(hours / 24)

function buildTags(): MockTag[] {
  const workspace_id = ids.sharmaSweets
  return [
    ...seedTags.map((tag) => ({ ...tag, workspace_id })),
    { id: mockTagIds.vip, name: 'VIP', color: '#1f5a8c', created_at: daysAgo(85), workspace_id },
    { id: mockTagIds.mumbai, name: 'Mumbai', color: '', created_at: daysAgo(50), workspace_id },
    { id: mockTagIds.bengaluru, name: 'Bengaluru', color: '', created_at: daysAgo(50), workspace_id },
    { id: mockTagIds.jaipur, name: 'Jaipur', color: '#8a5d0c', created_at: daysAgo(50), workspace_id },
    { id: mockTagIds.corporate, name: 'Corporate gifting', color: '#5c6a63', created_at: daysAgo(30), workspace_id },
    { id: 'c1d2e3f4-a5b6-4c7d-8e9f-0a1b2c3d4e71', name: 'Recall due', color: '#1d7f55', created_at: daysAgo(30), workspace_id: ids.kaveriClinic },
  ]
}

const sweets = ['Kaju Katli 1 kg', 'Motichoor Ladoo 500 g', 'Ghewar box', 'Soan Papdi gift pack', 'Rasgulla tin']

function buildSharma(events: MockConsentEvent[]): MockContact[] {
  let eventCount = 0
  const addEvent = (contact: MockContact, event: Omit<MockConsentEvent, 'id' | 'workspace_id' | 'contact_id' | 'purpose' | 'wamid' | 'created_at'> & { wamid?: string }) => {
    eventCount += 1
    events.push({
      id: eventId(eventCount),
      workspace_id: contact.workspace_id,
      contact_id: contact.id,
      purpose: 'marketing',
      wamid: event.wamid ?? '',
      created_at: event.occurred_at,
      ...event,
    })
  }

  return Array.from({ length: 60 }, (_, i) => {
    const city = i % 5 === 0 ? 'Mumbai' : i % 5 === 1 ? 'Bengaluru' : i % 5 === 2 ? 'Jaipur' : indianCities[i % indianCities.length]
    const status: MockContact['marketing_opt_in_status'] = i % 9 === 4 ? 'opted_out' : i % 3 === 0 ? 'unknown' : 'opted_in'
    const phone = indianMobile(i)
    const name = i % 17 === 16 ? '' : indianName(i)
    const tags: string[] = []
    if (i % 2 === 0) tags.push(mockTagIds.regular)
    if (i % 4 === 0) tags.push(mockTagIds.diwali)
    if (i % 7 === 2) tags.push(mockTagIds.wholesale)
    if (i % 10 === 1) tags.push(mockTagIds.vip)
    if (city === 'Mumbai') tags.push(mockTagIds.mumbai)
    if (city === 'Bengaluru') tags.push(mockTagIds.bengaluru)
    if (city === 'Jaipur') tags.push(mockTagIds.jaipur)
    if (i % 11 === 5) tags.push(mockTagIds.corporate)

    const attributes: Record<string, string> = { city }
    if (i % 3 !== 2) attributes.last_order = sweets[i % sweets.length]
    if (i % 7 === 2) attributes.gstin = `08AAB${String(1000 + i)}C1Z${i % 10}`

    const createdDays = 90 - i
    const contact: MockContact = {
      id: contactId(i),
      workspace_id: ids.sharmaSweets,
      phone_e164: phone,
      wa_id: phone.slice(1),
      name,
      email: i % 4 === 0 && name ? `${name.toLowerCase().replace(/\s/g, '.')}@gmail.com` : '',
      attributes,
      tags,
      marketing_opt_in_status: status,
      opted_in_at: null,
      opted_out_at: null,
      opt_in_source: '',
      last_inbound_at: i % 5 === 0 ? hoursAgo((i % 3) * 20 + 2) : i % 7 === 3 ? daysAgo(12) : null,
      created_at: daysAgo(createdDays),
      updated_at: daysAgo(Math.max(0, createdDays - 5)),
    }

    const optInAt = daysAgo(createdDays - 1)
    if (status === 'opted_in' || status === 'opted_out') {
      const source = i % 4 === 1 ? 'import' : i % 4 === 2 ? 'manual' : i % 4 === 3 ? 'whatsapp_keyword' : 'api'
      contact.opted_in_at = optInAt
      contact.opt_in_source = source
      addEvent(contact, {
        action: 'opt_in',
        source,
        evidence:
          source === 'import'
            ? 'Contact import; consent attested by the uploader. Opt-in source: Checkout form on sharmasweets.in'
            : source === 'manual'
              ? 'Ticked "Send me offers on WhatsApp" on the billing counter form.'
              : source === 'whatsapp_keyword'
                ? ''
                : 'Opted in on the website checkout page.',
        actor: source === 'manual' ? ids.priya : source === 'import' ? ids.demoUser : null,
        wamid: source === 'whatsapp_keyword' ? `wamid.HBgMOTE${i}START` : '',
        occurred_at: optInAt,
      })
    }
    if (status === 'opted_out') {
      const source = i % 2 === 0 ? 'whatsapp_keyword' : 'meta_marketing_optout'
      contact.opted_out_at = daysAgo(3 + (i % 5))
      addEvent(contact, {
        action: 'opt_out',
        source,
        evidence: '',
        actor: null,
        wamid: source === 'whatsapp_keyword' ? `wamid.HBgMOTE${i}STOP` : '',
        occurred_at: contact.opted_out_at,
      })
    }
    return contact
  })
}

function buildKaveri(): MockContact[] {
  return Array.from({ length: 6 }, (_, i) => {
    const phone = indianMobile(100 + i)
    return {
      id: kaveriContactId(i),
      workspace_id: ids.kaveriClinic,
      phone_e164: phone,
      wa_id: phone.slice(1),
      name: indianName(40 + i),
      email: '',
      attributes: { city: 'Bengaluru' },
      tags: [],
      marketing_opt_in_status: 'unknown',
      opted_in_at: null,
      opted_out_at: null,
      opt_in_source: '',
      last_inbound_at: null,
      created_at: daysAgo(30 - i),
      updated_at: daysAgo(30 - i),
    }
  })
}

function buildConversations(contacts: MockContact[]): MockConversation[] {
  return contacts
    .filter((contact) => contact.workspace_id === ids.sharmaSweets && contact.last_inbound_at)
    .map((contact, index) => ({
      id: conversationId(index),
      workspace_id: contact.workspace_id,
      contact: {
        id: contact.id,
        name: contact.name ?? '',
        phone_e164: contact.phone_e164,
        marketing_opt_in_status: contact.marketing_opt_in_status,
      },
      phone_number: { id: ids.phoneMain, display_phone_number: '+91 98290 11223', verified_name: 'Sharma Sweets' },
      status: 'open',
      assignee: null,
      unread_count: 0,
      last_message_at: contact.last_inbound_at,
      last_inbound_at: contact.last_inbound_at,
      service_window_expires_at: null,
      window_open: false,
      last_message: null,
      created_at: contact.created_at,
      updated_at: contact.last_inbound_at ?? contact.created_at,
    }))
}

function build(): ContactsMockState {
  const consentEvents: MockConsentEvent[] = []
  const contacts = [...buildSharma(consentEvents), ...buildKaveri()]
  return {
    tags: buildTags(),
    contacts,
    consentEvents,
    imports: [],
    conversations: buildConversations(contacts),
  }
}

let current: ContactsMockState | null = null
let builtFor: unknown = null

/** The contacts mock state for the current mock database. */
export function contactsMock(): ContactsMockState {
  if (!current || builtFor !== db.generation) {
    current = build()
    builtFor = db.generation
  }
  return current
}
