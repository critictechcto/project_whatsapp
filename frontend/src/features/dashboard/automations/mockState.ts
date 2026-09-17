/**
 * In-memory automation data for mock mode and tests, rebuilt whenever the shared mock database
 * is reset (before each test).
 */
import type { Schemas } from '../../../api/types'
import { db, type Mutable } from '../../../mocks/db'
import { ids, seedTags, seedTemplates } from '../../../mocks/seed'

export type MockRule = Mutable<Schemas['AutomationRule']>
export type RuleRecord = { workspaceId: string; rule: MockRule }
export type RunRecord = { workspaceId: string; run: Schemas['AutomationRun'] }
export type MockBusinessHours = { enabled: boolean; schedule: Schemas['BusinessHoursSlot'][] }

export const ruleIds = {
  price: 'a17c0000-0000-4000-8000-000000000001',
  welcome: 'a17c0000-0000-4000-8000-000000000002',
  away: 'a17c0000-0000-4000-8000-000000000003',
  diwali: 'a17c0000-0000-4000-8000-000000000004',
} as const

function build() {
  const now = Date.now()
  const hoursAgo = (hours: number) => new Date(now - hours * 3_600_000).toISOString()
  const daysAgo = (days: number) => hoursAgo(days * 24)
  const rule = (fields: Omit<MockRule, 'created_at' | 'updated_at'> & { createdDaysAgo: number }): RuleRecord => {
    const { createdDaysAgo, ...rest } = fields
    return { workspaceId: ids.sharmaSweets, rule: { ...rest, created_at: daysAgo(createdDaysAgo), updated_at: daysAgo(Math.max(0, createdDaysAgo - 5)) } }
  }

  const rules: RuleRecord[] = [
    rule({
      id: ruleIds.price,
      name: 'PRICE keyword reply',
      is_active: true,
      trigger: 'keyword',
      keywords: ['price', 'rate list'],
      keyword_match: 'contains',
      phone_number_id: null,
      actions: [
        {
          type: 'send_text',
          config: {
            text: 'Namaste! This week’s prices: Kaju katli ₹1,200/kg, Motichoor laddoo ₹640/kg, Soan papdi ₹480/kg. Reply ORDER and our team will take it from there.',
          },
        },
      ],
      cooldown_minutes: 60,
      priority: 0,
      stop_processing: false,
      run_count: 58,
      last_triggered_at: hoursAgo(2),
      createdDaysAgo: 40,
    }),
    rule({
      id: ruleIds.welcome,
      name: 'Welcome message',
      is_active: true,
      trigger: 'new_contact',
      keywords: [],
      keyword_match: 'exact',
      phone_number_id: null,
      actions: [
        { type: 'send_text', config: { text: 'Welcome to Sharma Sweets! Tell us what you’re looking for, or reply PRICE for this week’s rate list.' } },
        { type: 'assign', config: { user_id: ids.priya } },
      ],
      cooldown_minutes: 0,
      priority: 1,
      stop_processing: false,
      run_count: 112,
      last_triggered_at: hoursAgo(5),
      createdDaysAgo: 38,
    }),
    rule({
      id: ruleIds.away,
      name: 'Away message',
      is_active: true,
      trigger: 'outside_business_hours',
      keywords: [],
      keyword_match: 'exact',
      phone_number_id: null,
      actions: [
        {
          type: 'send_text',
          config: { text: 'Thanks for your message! We’re open Monday to Saturday, 10 am to 7 pm. We’ll reply as soon as we open.' },
        },
      ],
      cooldown_minutes: 240,
      priority: 2,
      stop_processing: true,
      run_count: 31,
      last_triggered_at: hoursAgo(14),
      createdDaysAgo: 36,
    }),
    rule({
      id: ruleIds.diwali,
      name: 'Diwali order keyword',
      is_active: false,
      trigger: 'keyword',
      keywords: ['diwali', 'gift box'],
      keyword_match: 'exact',
      phone_number_id: null,
      actions: [
        {
          type: 'send_template',
          config: {
            template_id: seedTemplates[1].id,
            body_params: [
              { source: 'contact_field', value: 'name', fallback: 'there' },
              { source: 'static', value: '20 Oct', fallback: '' },
            ],
          },
        },
        { type: 'add_tags', config: { tag_ids: [seedTags[1].id] } },
      ],
      cooldown_minutes: 1440,
      priority: 3,
      stop_processing: false,
      run_count: 0,
      last_triggered_at: null,
      createdDaysAgo: 6,
    }),
  ]

  const hours = new Map<string, MockBusinessHours>([
    [ids.sharmaSweets, { enabled: true, schedule: [0, 1, 2, 3, 4, 5].map((day) => ({ day, start: '10:00', end: '19:00' })) }],
  ])

  const cycle = [rules[0].rule, rules[1].rule, rules[2].rule]
  const success: Record<string, string> = {
    [ruleIds.price]: 'Sent the price list reply.',
    [ruleIds.welcome]: 'Sent the welcome message and assigned the conversation to Priya.',
    [ruleIds.away]: 'Sent the away message.',
  }
  const runs: RunRecord[] = Array.from({ length: 25 }, (_, i) => {
    const source = cycle[i % cycle.length]
    const status: Schemas['AutomationRunStatusEnum'] = i % 7 === 3 ? 'skipped' : i % 11 === 5 ? 'failed' : 'succeeded'
    const detail =
      status === 'skipped'
        ? `Skipped: the rule already ran for this conversation in the last ${source.cooldown_minutes || 60} minutes.`
        : status === 'failed'
          ? "Meta didn't accept the reply because the 24-hour customer service window had closed (131047)."
          : success[source.id]
    const suffix = String(i + 1).padStart(12, '0')
    return {
      workspaceId: ids.sharmaSweets,
      run: {
        id: `b17c0000-0000-4000-8000-${suffix}`,
        rule: { id: source.id, name: source.name },
        conversation_id: `c0a1b2c3-d4e5-4f60-8a1b-${suffix}`,
        message_id: `d0a1b2c3-d4e5-4f60-8a1b-${suffix}`,
        status,
        detail,
        created_at: hoursAgo(i * 2.5 + 0.5),
      },
    }
  })

  return { rules, hours, runs }
}

let snapshot: { token: unknown; state: ReturnType<typeof build> } | null = null

export function automationState() {
  if (!snapshot || snapshot.token !== db.generation) snapshot = { token: db.generation, state: build() }
  return snapshot.state
}

export function hoursFor(workspaceId: string): MockBusinessHours {
  const { hours } = automationState()
  let entry = hours.get(workspaceId)
  if (!entry) {
    entry = { enabled: false, schedule: [] }
    hours.set(workspaceId, entry)
  }
  return entry
}

export function workspaceTimeZone(workspaceId: string): string {
  return db.workspaces.find((workspace) => workspace.id === workspaceId)?.time_zone || 'Asia/Kolkata'
}
