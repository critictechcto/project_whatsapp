/**
 * In-memory campaign data for mock mode and tests. Rebuilt whenever the shared mock database is
 * reset (tests reset it before each test), so every test starts from the same seed.
 */
import type { Schemas } from '../../../api/types'
import { db, type Mutable } from '../../../mocks/db'
import { ids, indianMobile, indianName, seedPhoneNumber, seedTags, seedTemplates, seedUsers } from '../../../mocks/seed'

type Campaign = Schemas['Campaign']
type CampaignStatus = Schemas['CampaignStatusEnum']
type CampaignStats = Schemas['CampaignStats']
type RecipientStatus = Schemas['RecipientStatusEnum']
type Audience = Schemas['CampaignAudienceRequest']
type Mapping = Schemas['VariableMappingRequest']
type TemplateCategory = Schemas['MessageTemplateCategoryEnum']
type OptInStatus = Schemas['ContactOptInStatusEnum']

export type MockContact = {
  id: string
  name: string
  phone_e164: string
  email: string
  attributes: Record<string, string>
  tags: string[]
  marketing_opt_in_status: OptInStatus
}

export type MockRecipient = Mutable<Schemas['CampaignRecipient']> & {
  replied: boolean
  /** Won't move to another status any more. */
  settled: boolean
}

export type CampaignRecord = { workspaceId: string; campaign: Mutable<Campaign>; recipients: MockRecipient[] }

export type SkipReason = 'opted_out' | 'not_opted_in' | 'invalid'

export const campaignIds = {
  diwali: '6b0e2c4a-8d1f-4e3b-9a5c-7f2d1e0c0001',
  orderShipped: '6b0e2c4a-8d1f-4e3b-9a5c-7f2d1e0c0002',
  monsoon: '6b0e2c4a-8d1f-4e3b-9a5c-7f2d1e0c0003',
  navratri: '6b0e2c4a-8d1f-4e3b-9a5c-7f2d1e0c0004',
  wholesaleDraft: '6b0e2c4a-8d1f-4e3b-9a5c-7f2d1e0c0005',
} as const

export const mockTagIds = { regular: seedTags[0].id, diwali: seedTags[1].id, wholesale: seedTags[2].id } as const

const templateIds = { orderShipped: seedTemplates[0].id, diwali: seedTemplates[1].id } as const

const cities = ['Jaipur', 'Delhi', 'Mumbai', 'Pune'] as const

/** Same 48 contacts (ids, consent, tags) as the shared `/api/v1/contacts/` fallback. */
export function mockContacts(workspaceId: string): MockContact[] {
  if (workspaceId !== ids.sharmaSweets) return []
  return Array.from({ length: 48 }, (_, i) => {
    const status: OptInStatus = i % 9 === 4 ? 'opted_out' : i % 3 === 0 ? 'unknown' : 'opted_in'
    const name = indianName(i)
    return {
      id: `e0f1a2b3-c4d5-4e6f-8a9b-${String(i + 1).padStart(12, '0')}`,
      name,
      phone_e164: indianMobile(i),
      email: i % 4 === 0 ? `${name.toLowerCase().replace(/\s/g, '.')}@gmail.com` : '',
      attributes: { city: cities[i % 4] },
      tags: i % 2 === 0 ? [mockTagIds.regular] : [],
      marketing_opt_in_status: status,
    }
  })
}

export function mockTemplate(workspaceId: string, templateId: string | null | undefined) {
  if (workspaceId !== ids.sharmaSweets || !templateId) return undefined
  return seedTemplates.find((template) => template.id === templateId)
}

function skipReason(contact: MockContact, category: TemplateCategory): SkipReason | '' {
  if (!/^\+[1-9]\d{7,14}$/.test(contact.phone_e164)) return 'invalid'
  if (contact.marketing_opt_in_status === 'opted_out') return 'opted_out'
  if (category === 'MARKETING' && contact.marketing_opt_in_status !== 'opted_in') return 'not_opted_in'
  return ''
}

/** Who an audience matches and who of them would be skipped, like the backend's materialisation. */
export function evaluateAudience(workspaceId: string, audience: Audience, category: TemplateCategory) {
  const tagIds = audience.tag_ids ?? []
  const contactIds = audience.contact_ids ?? []
  const matched = mockContacts(workspaceId).filter((contact) => {
    const byTag =
      tagIds.length > 0 &&
      (audience.match === 'all' ? tagIds.every((id) => contact.tags.includes(id)) : tagIds.some((id) => contact.tags.includes(id)))
    return byTag || contactIds.includes(contact.id)
  })
  const entries = matched.map((contact) => ({ contact, skip: skipReason(contact, category) }))
  const count = (reason: SkipReason) => entries.filter((entry) => entry.skip === reason).length
  const preview: Schemas['AudiencePreview'] = {
    total: entries.length,
    eligible: entries.filter((entry) => !entry.skip).length,
    skipped: { opted_out: count('opted_out'), not_opted_in: count('not_opted_in'), invalid: count('invalid') },
  }
  return { entries, preview }
}

/** Approximate per-message rates in INR for the mock estimate only. */
const MOCK_RATE_INR: Record<TemplateCategory, number> = { MARKETING: 0.7846, UTILITY: 0.115, AUTHENTICATION: 0.115 }

export function estimateCost(recipients: number, category: TemplateCategory): Schemas['CostEstimate'] {
  return {
    currency: 'INR',
    amount: (recipients * MOCK_RATE_INR[category]).toFixed(4),
    note: "Approximate, under Meta's current rates for India, excluding taxes. Meta sets the final charges, which can differ.",
  }
}

const emptyStats: CampaignStats = { total: 0, skipped: 0, queued: 0, sent: 0, delivered: 0, read: 0, failed: 0, replied: 0 }

export function computeStats(recipients: readonly MockRecipient[]): CampaignStats {
  const count = (...statuses: RecipientStatus[]) => recipients.filter((recipient) => statuses.includes(recipient.status)).length
  return {
    total: recipients.length,
    skipped: count('skipped'),
    queued: count('pending', 'queued'),
    sent: count('sent', 'delivered', 'read'),
    delivered: count('delivered', 'read'),
    read: count('read'),
    failed: count('failed'),
    replied: recipients.filter((recipient) => recipient.replied).length,
  }
}

/** Recomputes stats and the cost estimate after a change. */
export function refreshCampaign(record: CampaignRecord) {
  const campaign = record.campaign
  if (record.recipients.length) {
    campaign.stats = computeStats(record.recipients)
    campaign.estimated_cost = estimateCost(campaign.stats.total - campaign.stats.skipped, campaign.template.category)
    return
  }
  const { preview } = evaluateAudience(record.workspaceId, campaign.audience, campaign.template.category)
  campaign.stats = { ...emptyStats, total: preview.total, skipped: preview.total - preview.eligible }
  campaign.estimated_cost = estimateCost(preview.eligible, campaign.template.category)
}

/** Snapshots the audience into recipients, as launch does. */
export function materialise(record: CampaignRecord, at: string) {
  const { entries } = evaluateAudience(record.workspaceId, record.campaign.audience, record.campaign.template.category)
  const ordered = [...entries.filter((entry) => !entry.skip), ...entries.filter((entry) => entry.skip)]
  record.recipients = ordered.map(({ contact, skip }) => ({
    id: crypto.randomUUID(),
    contact: {
      id: contact.id,
      name: contact.name,
      phone_e164: contact.phone_e164,
      marketing_opt_in_status: contact.marketing_opt_in_status,
    },
    status: skip ? 'skipped' : 'pending',
    skip_reason: skip,
    error_code: '',
    message_id: null,
    updated_at: at,
    replied: false,
    settled: Boolean(skip),
  }))
}

type ProgressStep = { status: RecipientStatus; errorCode?: string; replied?: boolean }

type Seed = {
  id: string
  name: string
  templateId: string
  audience: Audience
  mapping: Mapping
  status: CampaignStatus
  createdBy: (typeof seedUsers)[number]
  createdAt: string
  scheduledAt?: string | null
  startedAt?: string | null
  completedAt?: string | null
  lastError?: string
  /** Statuses of the first eligible recipients, in order; the rest stay pending. */
  progress?: ProgressStep[]
}

export function phoneSummary(): Schemas['ConversationPhoneNumber'] {
  return {
    id: seedPhoneNumber.id,
    display_phone_number: seedPhoneNumber.display_phone_number,
    verified_name: seedPhoneNumber.verified_name,
  }
}

export function templateRef(template: NonNullable<ReturnType<typeof mockTemplate>>): Schemas['CampaignTemplate'] {
  return { id: template.id, name: template.name, language: template.language, category: template.category }
}

function createRecord(workspaceId: string, seed: Seed): CampaignRecord {
  const template = mockTemplate(workspaceId, seed.templateId)!
  const record: CampaignRecord = {
    workspaceId,
    campaign: {
      id: seed.id,
      name: seed.name,
      status: seed.status,
      template: templateRef(template),
      phone_number: phoneSummary(),
      audience: seed.audience,
      variable_mapping: seed.mapping,
      scheduled_at: seed.scheduledAt ?? null,
      started_at: seed.startedAt ?? null,
      completed_at: seed.completedAt ?? null,
      consent_attested: seed.status !== 'draft',
      stats: emptyStats,
      estimated_cost: null,
      last_error: seed.lastError ?? '',
      created_by: { id: seed.createdBy.id, full_name: seed.createdBy.full_name, email: seed.createdBy.email },
      created_at: seed.createdAt,
      updated_at: seed.startedAt ?? seed.createdAt,
    },
    recipients: [],
  }

  if (seed.startedAt) {
    materialise(record, seed.startedAt)
    const finished = seed.status === 'completed'
    record.recipients
      .filter((recipient) => recipient.status !== 'skipped')
      .forEach((recipient, index) => {
        const step = seed.progress?.[index]
        if (!step) return
        recipient.status = step.status
        recipient.error_code = step.errorCode ?? ''
        recipient.replied = Boolean(step.replied)
        recipient.message_id = step.status === 'pending' || step.status === 'queued' ? null : crypto.randomUUID()
        recipient.settled = finished || step.status === 'read' || step.status === 'failed'
      })
  }
  refreshCampaign(record)
  return record
}

function build(): CampaignRecord[] {
  const now = Date.now()
  const hoursAgo = (hours: number) => new Date(now - hours * 3_600_000).toISOString()
  const [rohan, priya] = seedUsers
  const contactId = (i: number) => `e0f1a2b3-c4d5-4e6f-8a9b-${String(i + 1).padStart(12, '0')}`
  const greeting: Mapping = {
    header: null,
    body: [
      { source: 'contact_field', value: 'name', fallback: 'there' },
      { source: 'static', value: '20 Oct', fallback: '' },
    ],
    buttons: {},
  }
  const inThreeDays = new Date(now)
  inThreeDays.setUTCDate(inThreeDays.getUTCDate() + 3)
  inThreeDays.setUTCHours(4, 30, 0, 0) // 10:00 IST

  const read = (replied = false): ProgressStep => ({ status: 'read', replied })
  const step = (status: RecipientStatus, errorCode?: string): ProgressStep => ({ status, errorCode })

  const seeds: Seed[] = [
    {
      id: campaignIds.diwali,
      name: 'Diwali sale 2026',
      templateId: templateIds.diwali,
      audience: { tag_ids: [mockTagIds.regular], match: 'any', contact_ids: [] },
      mapping: greeting,
      status: 'running',
      createdBy: priya,
      createdAt: hoursAgo(26),
      startedAt: hoursAgo(0.7),
      progress: [read(true), read(), read(), read(), step('delivered'), step('delivered'), step('sent'), step('sent'), step('queued')],
    },
    {
      id: campaignIds.orderShipped,
      name: 'Order shipped update',
      templateId: templateIds.orderShipped,
      audience: { tag_ids: [], match: 'any', contact_ids: Array.from({ length: 12 }, (_, i) => contactId(i)) },
      mapping: {
        header: { source: 'attribute', value: 'order_id', fallback: 'update' },
        body: [
          { source: 'contact_field', value: 'name', fallback: 'there' },
          { source: 'attribute', value: 'last_order', fallback: 'sweets' },
          { source: 'static', value: '14 Sep', fallback: '' },
        ],
        buttons: { '0': { source: 'attribute', value: 'order_id', fallback: 'orders' } },
      },
      status: 'completed',
      createdBy: rohan,
      createdAt: hoursAgo(150),
      startedAt: hoursAgo(144),
      completedAt: hoursAgo(143),
      progress: [
        read(true),
        read(),
        read(true),
        read(),
        read(),
        read(),
        read(),
        read(),
        step('delivered'),
        step('delivered'),
        step('failed', '131026'),
      ],
    },
    {
      id: campaignIds.monsoon,
      name: 'Monsoon offer',
      templateId: templateIds.diwali,
      audience: { tag_ids: [mockTagIds.regular], match: 'any', contact_ids: [contactId(1), contactId(5), contactId(7)] },
      mapping: { ...greeting, body: [greeting.body![0], { source: 'static', value: '30 Sep', fallback: '' }] },
      status: 'paused',
      createdBy: priya,
      createdAt: hoursAgo(80),
      startedAt: hoursAgo(50),
      lastError:
        'Paused automatically because the quality rating Meta reports for +91 98290 11223 dropped to Low. Sending more marketing messages now could lower your messaging limit. Review recent customer feedback, then resume when you are ready.',
      progress: [
        read(),
        read(),
        read(true),
        read(),
        read(),
        step('delivered'),
        step('delivered'),
        step('delivered'),
        step('failed', '131049'),
        step('failed', '131049'),
      ],
    },
    {
      id: campaignIds.navratri,
      name: 'Navratri greetings',
      templateId: templateIds.diwali,
      audience: { tag_ids: [mockTagIds.regular], match: 'any', contact_ids: [] },
      mapping: { ...greeting, body: [greeting.body![0], { source: 'static', value: '12 Oct', fallback: '' }] },
      status: 'scheduled',
      createdBy: rohan,
      createdAt: hoursAgo(20),
      scheduledAt: inThreeDays.toISOString(),
    },
    {
      id: campaignIds.wholesaleDraft,
      name: 'Wholesale Diwali orders',
      templateId: templateIds.diwali,
      audience: { tag_ids: [mockTagIds.wholesale], match: 'any', contact_ids: [] },
      mapping: greeting,
      status: 'draft',
      createdBy: rohan,
      createdAt: hoursAgo(4),
    },
  ]

  return seeds.map((seed) => createRecord(ids.sharmaSweets, seed))
}

let snapshot: { token: unknown; records: CampaignRecord[] } | null = null

/** All campaign records. `db.generation` is replaced by `resetMockDb()`, which triggers a rebuild. */
export function campaignRecords(): CampaignRecord[] {
  if (!snapshot || snapshot.token !== db.generation) snapshot = { token: db.generation, records: build() }
  return snapshot.records
}

export function findCampaign(workspaceId: string, id: string): CampaignRecord | undefined {
  return campaignRecords().find((record) => record.workspaceId === workspaceId && record.campaign.id === id)
}

export function toCampaign(record: CampaignRecord): Campaign {
  return { ...record.campaign }
}

export function toRecipient({ replied: _replied, settled: _settled, ...recipient }: MockRecipient): Schemas['CampaignRecipient'] {
  return recipient
}

/** Moves a running campaign's recipients one stage along. Returns false when nothing is left to move. */
function advance(record: CampaignRecord, at: string): boolean {
  const marketing = record.campaign.template.category === 'MARKETING'
  let changed = false
  const move = (from: RecipientStatus, apply: (recipient: MockRecipient, index: number) => void, limit = 1) => {
    let moved = 0
    record.recipients.forEach((recipient, index) => {
      if (moved >= limit || recipient.status !== from || recipient.settled) return
      apply(recipient, index)
      recipient.updated_at = at
      moved += 1
      changed = true
    })
  }
  // Later stages first, so a recipient moves at most one stage per tick.
  move('delivered', (recipient, index) => {
    if (index % 10 < 7) {
      recipient.status = 'read'
      recipient.replied = index % 5 === 0
    }
    recipient.settled = true
  })
  move('sent', (recipient, index) => {
    if (marketing && index % 9 === 7) {
      recipient.status = 'failed'
      recipient.error_code = '131049'
      recipient.settled = true
    } else {
      recipient.status = 'delivered'
    }
  })
  move('queued', (recipient) => {
    recipient.status = 'sent'
    recipient.message_id = crypto.randomUUID()
  })
  move('pending', (recipient) => {
    recipient.status = 'queued'
  }, 2)
  return changed
}

/** One tick of the mock sender: starts due scheduled campaigns and progresses running ones. */
export function advanceCampaigns(now = Date.now()): CampaignRecord[] {
  const at = new Date(now).toISOString()
  const changed: CampaignRecord[] = []
  for (const record of campaignRecords()) {
    const campaign = record.campaign
    if (campaign.status === 'scheduled' && campaign.scheduled_at && new Date(campaign.scheduled_at).getTime() <= now) {
      materialise(record, at)
      campaign.status = 'running'
      campaign.started_at = at
    } else if (campaign.status === 'running') {
      if (!advance(record, at)) {
        campaign.status = 'completed'
        campaign.completed_at = at
      }
    } else {
      continue
    }
    campaign.updated_at = at
    refreshCampaign(record)
    changed.push(record)
  }
  return changed
}
