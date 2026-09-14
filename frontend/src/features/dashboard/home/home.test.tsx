import { screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { Schemas } from '../../../api/types'
import { server } from '../../../mocks/node'
import { daysAgo, ids } from '../../../mocks/seed'
import { errorResponse, http, paginate } from '../../../mocks/utils'
import { renderDashboard, signIn } from '../../../test/render'
import { campaignProgress, summarizeTemplates, tierLabel, trialDaysLeft } from './api'

const home = `/app/w/${ids.sharmaSweets}`
const empty = { next: null, previous: null, results: [] }

const user = { id: ids.demoUser, email: 'demo@upchatz.com', full_name: 'Rohan Sharma' }

function campaign(overrides: Partial<Schemas['Campaign']> = {}): Schemas['Campaign'] {
  return {
    id: '9c1f5e2a-4b3d-4e6f-8a7b-0c1d2e3f4a51',
    name: 'Diwali early access',
    status: 'running',
    template: { id: 'a4e1c3b5-7d9f-4b2a-8c6e-0f1a2b3c4d52', name: 'diwali_early_access', language: 'en', category: 'MARKETING' },
    phone_number: { id: ids.phoneMain, display_phone_number: '+91 98290 11223', verified_name: 'Sharma Sweets' },
    audience: { tag_ids: [], match: 'any', contact_ids: [] },
    variable_mapping: {},
    scheduled_at: null,
    started_at: daysAgo(1),
    completed_at: null,
    consent_attested: true,
    stats: { total: 200, skipped: 10, queued: 90, sent: 40, delivered: 40, read: 20, failed: 0, replied: 3 },
    estimated_cost: null,
    last_error: '',
    created_by: user,
    created_at: daysAgo(2),
    updated_at: daysAgo(1),
    ...overrides,
  } as Schemas['Campaign']
}

type HomeMocks = {
  campaigns?: 'empty' | 'sent' | 501
  automations?: 'empty' | 'some' | 501
  conversations?: 'counts' | 501
  subscription?: 'trial' | 501
  inviteSent?: boolean
  members?: number
}

/**
 * Handlers for areas whose mocks aren't part of this branch. The members list is mocked here too:
 * the shared `/workspaces/{id}/` handler currently matches `/workspaces/members/` first.
 */
function useHomeMocks({
  campaigns = 'empty',
  automations = 'empty',
  conversations = 'counts',
  subscription = 'trial',
  inviteSent = false,
  members = 3,
}: HomeMocks) {
  const notImplemented = () => errorResponse(501, 'not_implemented', 'This endpoint is not available yet.')
  server.use(
    http.get('/api/v1/workspaces/members/', ({ request, response }) => {
      const results = Array.from({ length: members }, (_, i) => ({
        id: `membership-${i}`,
        role: i === 0 ? 'owner' : 'agent',
        created_at: daysAgo(10),
        user: { ...user, id: `user-${i}` },
      })) as Schemas['Membership'][]
      return response(200).json(paginate(request, results))
    }),
    http.get('/api/v1/campaigns/', ({ request, response }) => {
      if (campaigns === 501) return response.untyped(notImplemented())
      return response(200).json(paginate(request, campaigns === 'sent' ? [campaign()] : []))
    }),
    http.get('/api/v1/automations/rules/', ({ response }) => {
      if (automations === 501) return response.untyped(notImplemented())
      if (automations === 'empty') return response(200).json(empty)
      return response(200).json({
        ...empty,
        results: [
          {
            id: 'b2c3d4e5-f6a7-4b8c-9d0e-1f2a3b4c5d61',
            name: 'Price list keyword',
            is_active: true,
            trigger: 'keyword',
            keywords: ['price'],
            keyword_match: 'exact',
            phone_number_id: null,
            actions: [],
            cooldown_minutes: 0,
            priority: 0,
            stop_processing: false,
            run_count: 4,
            last_triggered_at: daysAgo(1),
            created_at: daysAgo(10),
            updated_at: daysAgo(1),
          },
        ],
      } as Schemas['PaginatedAutomationRuleList'])
    }),
    http.get('/api/v1/inbox/conversations/', ({ query, response }) => {
      if (conversations === 501) return response.untyped(notImplemented())
      const unassigned = query.get('assignee') === 'none'
      const count = unassigned ? 3 : 12
      const results = Array.from({ length: count }, (_, i) => ({ id: `conversation-${i}` })) as unknown as Schemas['Conversation'][]
      return response(200).json({ ...empty, results })
    }),
    http.get('/api/v1/billing/subscription/', ({ response }) => {
      if (subscription === 501) return response.untyped(notImplemented())
      return response(200).json({
        plan: { id: 'growth', name: 'Growth', monthly_price_paise: 0, annual_price_paise: 0, limits: { whatsapp_numbers: 1, members: 5, contacts: null }, features: [] },
        status: 'trialing',
        interval: 'monthly',
        trial_ends_at: new Date(Date.now() + 5.5 * 24 * 60 * 60 * 1000).toISOString(),
        current_period_start: null,
        current_period_end: null,
        cancel_at_period_end: false,
      } as Schemas['Subscription'])
    }),
    http.get('/api/v1/workspaces/invitations/', ({ response }) =>
      response(200).json(
        inviteSent
          ? ({ ...empty, results: [{ id: 'inv-1', email: 'meera@sharmasweets.in', role: 'agent', status: 'pending', invited_by: user, expires_at: daysAgo(-5), created_at: daysAgo(1) }] } as Schemas['PaginatedInvitationList'])
          : empty,
      ),
    ),
  )
}

async function checklist() {
  await screen.findByRole('heading', { level: 1, name: 'Welcome, Rohan' }, { timeout: 10_000 })
  const heading = await screen.findByRole('heading', { level: 2, name: /Get started|Setup complete/ })
  return heading.closest('section')!
}

describe('home checklist', () => {
  it('marks steps done from real data', async () => {
    useHomeMocks({})
    signIn()
    renderDashboard(home)
    const section = await checklist()

    await waitFor(() => expect(within(section).getByText('4 of 6 done')).toBeInTheDocument())
    const item = (title: string) => within(section).getByText(title).closest('li')!
    // Seeded: a number, contacts, templates, and other members in Sharma Sweets.
    for (const title of ['Connect WhatsApp', 'Add contacts', 'Create a template', 'Invite your team']) {
      expect(within(item(title)).getByLabelText('Done')).toBeInTheDocument()
    }
    expect(within(item('Send your first campaign')).getByLabelText('Not done')).toBeInTheDocument()
    expect(within(item('Send your first campaign')).getByRole('link', { name: /New campaign/ })).toHaveAttribute('href', `${home}/campaigns/new`)
    expect(within(item('Set up an automation')).getByLabelText('Not done')).toBeInTheDocument()
  })

  it('collapses once every step is done and can be reopened', async () => {
    useHomeMocks({ campaigns: 'sent', automations: 'some' })
    signIn()
    const { user } = renderDashboard(home)
    await screen.findByRole('heading', { level: 1, name: 'Welcome, Rohan' }, { timeout: 10_000 })

    const toggle = await screen.findByRole('button', { name: 'Show steps' }, { timeout: 10_000 })
    expect(screen.getByRole('heading', { name: 'Setup complete' })).toBeInTheDocument()
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByText('Connect WhatsApp')).not.toBeVisible()

    await user.click(toggle)
    expect(screen.getByRole('button', { name: 'Hide steps' })).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('Connect WhatsApp')).toBeVisible()
  })

  it("can't tell a step's state when its endpoint isn't available", async () => {
    useHomeMocks({ automations: 501 })
    signIn()
    renderDashboard(home)
    const section = await checklist()
    const item = await waitFor(() => within(section).getByText('Set up an automation').closest('li')!)
    await waitFor(() => expect(within(item).getByLabelText("Couldn't check")).toBeInTheDocument())
  })
})

describe('home overview cards', () => {
  it('shows counts, campaign progress and trial days from list endpoints', async () => {
    useHomeMocks({ campaigns: 'sent' })
    signIn()
    renderDashboard(home)

    const conversations = (await screen.findByRole('heading', { name: 'Conversations' }, { timeout: 10_000 })).closest('section')!
    await waitFor(() => expect(within(conversations).getByText('12')).toBeInTheDocument())
    expect(within(conversations).getByText('3')).toBeInTheDocument()

    const campaigns = screen.getByRole('heading', { name: 'Recent campaigns' }).closest('section')!
    await waitFor(() => expect(within(campaigns).getByText('Diwali early access')).toBeInTheDocument())
    expect(within(campaigns).getByRole('progressbar')).toHaveAttribute('aria-valuenow', '55')

    const plan = screen.getByRole('heading', { name: 'Plan' }).closest('section')!
    await waitFor(() => expect(within(plan).getByText('6 days left in your trial.')).toBeInTheDocument())

    const connection = screen.getByRole('heading', { name: 'WhatsApp connection' }).closest('section')!
    await waitFor(() => expect(within(connection).getByText('+91 98290 11223')).toBeInTheDocument())
    expect(within(connection).getByText('High quality')).toBeInTheDocument()
  })

  it('hides cards whose endpoint answers 501', async () => {
    useHomeMocks({ conversations: 501, subscription: 501, campaigns: 501 })
    signIn()
    renderDashboard(home)
    await screen.findByRole('heading', { name: 'WhatsApp connection' }, { timeout: 10_000 })
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Templates' })).toBeInTheDocument())
    await waitFor(() => {
      expect(screen.queryByRole('heading', { name: 'Conversations' })).not.toBeInTheDocument()
      expect(screen.queryByRole('heading', { name: 'Recent campaigns' })).not.toBeInTheDocument()
      expect(screen.queryByRole('heading', { name: 'Plan' })).not.toBeInTheDocument()
    })
  })

  it('counts invitations for the team step', async () => {
    useHomeMocks({ inviteSent: true, members: 1 })
    signIn()
    renderDashboard(`/app/w/${ids.kaveriClinic}`)
    await screen.findByRole('heading', { level: 1, name: 'Welcome, Rohan' }, { timeout: 10_000 })
    const section = (await screen.findByRole('heading', { level: 2, name: 'Get started' })).closest('section')!
    const item = within(section).getByText('Invite your team').closest('li')!
    await waitFor(() => expect(within(item).getByLabelText('Done')).toBeInTheDocument())
  })
})

describe('home helpers', () => {
  it('computes progress, trial days, tiers and template counts', () => {
    expect(campaignProgress({ total: 0, skipped: 0, queued: 0, sent: 0, delivered: 0, read: 0, failed: 0, replied: 0 }).percent).toBe(0)
    expect(trialDaysLeft('2026-09-12T00:00:00Z', Date.parse('2026-09-10T12:00:00Z'))).toBe(2)
    expect(trialDaysLeft('2026-09-01T00:00:00Z', Date.parse('2026-09-10T12:00:00Z'))).toBe(0)
    expect(tierLabel('TIER_1K')).toBe('1K')
    expect(tierLabel('TIER_UNLIMITED')).toBe('Unlimited')
    expect(tierLabel('')).toBeNull()
    expect(summarizeTemplates([{ status: 'APPROVED' }, { status: 'PAUSED' }, { status: 'DELETED' }], false)).toMatchObject({
      total: 2,
      approved: 1,
      attention: 1,
    })
  })
})
