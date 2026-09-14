import { act, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { RoleEnum } from '../../../api/types'
import { dispatch } from '../../../lib/realtime/registry'
import { db } from '../../../mocks/db'
import { ids } from '../../../mocks/seed'
import { renderDashboard, signIn } from '../../../test/render'
import { campaignIds, campaignRecords, findCampaign, toCampaign } from './mockState'
import { actionCopy } from './status'

const base = `/app/w/${ids.sharmaSweets}/campaigns`

function setRole(role: RoleEnum) {
  const membership = db.memberships.find((m) => m.workspace_id === ids.sharmaSweets && m.user_id === ids.demoUser)
  if (!membership) throw new Error('membership missing from seed')
  membership.role = role
}

function statValue(label: string) {
  const region = screen.getByRole('region', { name: 'Campaign numbers' })
  return within(region).getByText(label, { selector: 'dt' }).nextElementSibling?.textContent
}

describe('campaign wizard', () => {
  it('creates a campaign step by step and requires the consent attestation to launch', async () => {
    signIn()
    const { user, router } = renderDashboard(`${base}/new`)

    await user.type(await screen.findByLabelText(/^Campaign name/, {}, { timeout: 5000 }), 'Festive offer')
    await user.click(screen.getByRole('combobox', { name: /^Template/ }))
    await user.click(await screen.findByRole('option', { name: /diwali_early_access/ }))
    await user.click(screen.getByRole('button', { name: 'Save and continue' }))

    expect(await screen.findByRole('heading', { name: 'Choose who receives it' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Audience/ })).toHaveAttribute('aria-current', 'step')
    await user.click(screen.getByRole('combobox', { name: /^Tags/ }))
    await user.click(await screen.findByRole('option', { name: /Regular customer/ }))
    const preview = screen.getByRole('region', { name: 'Who receives it' })
    expect(await within(preview).findByText('13', {}, { timeout: 10_000 })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Save and continue' }))

    expect(await screen.findByRole('heading', { name: 'Fill in the variables' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Save and continue' }))
    const second = await screen.findByRole('group', { name: 'Body {{2}}' })
    expect(within(second).getByText('Enter the text to send.')).toBeInTheDocument()
    await user.type(within(second).getByLabelText(/^Text/), '20 Oct')
    await user.click(screen.getByRole('button', { name: 'Save and continue' }))

    expect(await screen.findByRole('heading', { name: 'Choose when to send' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Save and continue' }))

    expect(await screen.findByRole('heading', { name: 'Review and launch' })).toBeInTheDocument()
    expect(await screen.findByText(/Approximate, under Meta's current rates/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Launch campaign' }))
    expect(await screen.findByText('Confirm that these contacts agreed to receive WhatsApp messages from you.')).toBeInTheDocument()
    expect(campaignRecords().find((record) => record.campaign.name === 'Festive offer')?.campaign.status).toBe('draft')

    await user.click(screen.getByLabelText('I confirm these contacts agreed to receive WhatsApp messages from us'))
    await user.click(screen.getByRole('button', { name: 'Launch campaign' }))

    expect(await screen.findByRole('heading', { level: 1, name: 'Festive offer' }, { timeout: 10_000 })).toBeInTheDocument()
    const created = campaignRecords().find((record) => record.campaign.name === 'Festive offer')
    expect(created?.campaign.status).toBe('running')
    expect(created?.campaign.consent_attested).toBe(true)
    expect(created?.campaign.variable_mapping.body?.[1]).toEqual({ source: 'static', value: '20 Oct', fallback: '' })
    expect(router.state.location.pathname).toBe(`${base}/${created?.campaign.id}`)
  })

  it('updates the audience preview when tags change', async () => {
    signIn()
    const { user } = renderDashboard(`${base}/${campaignIds.wholesaleDraft}/edit?step=audience`)

    const preview = await screen.findByRole('region', { name: 'Who receives it' })
    await waitFor(() => expect(within(preview).getAllByText('0').length).toBeGreaterThan(0), { timeout: 10_000 })

    await user.click(screen.getByRole('combobox', { name: /^Tags/ }))
    await user.click(await screen.findByRole('option', { name: /Regular customer/ }))

    expect(await within(preview).findByText('24', {}, { timeout: 10_000 })).toBeInTheDocument()
    expect(within(preview).getByText('13')).toBeInTheDocument()
  })
})

describe('campaign report', () => {
  it('explains an invalid transition when the status changed in the meantime', async () => {
    signIn()
    const { user } = renderDashboard(`${base}/${campaignIds.diwali}`)
    expect(await screen.findByRole('heading', { level: 1, name: 'Diwali sale 2026' })).toBeInTheDocument()

    findCampaign(ids.sharmaSweets, campaignIds.diwali)!.campaign.status = 'completed'
    await user.click(screen.getByRole('button', { name: actionCopy.pause.label }))
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: actionCopy.pause.confirm }))

    expect(await screen.findByText(/That action isn't available for the campaign's current status/)).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByRole('button', { name: actionCopy.pause.label })).not.toBeInTheDocument())
  })

  it('applies live campaign.progress events to the stats', async () => {
    signIn()
    renderDashboard(`${base}/${campaignIds.diwali}`)
    expect(await screen.findByRole('heading', { level: 1, name: 'Diwali sale 2026' })).toBeInTheDocument()

    const stats = toCampaign(findCampaign(ids.sharmaSweets, campaignIds.diwali)!).stats
    expect(statValue('Sent')).toBe(String(stats.sent))

    act(() => {
      dispatch({
        v: 1,
        type: 'campaign.progress',
        workspace_id: ids.sharmaSweets,
        data: { campaign_id: campaignIds.diwali, status: 'running', stats: { ...stats, queued: 0, sent: 12, delivered: 11, read: 7 } },
      })
    })

    await waitFor(() => expect(statValue('Sent')).toBe('12'))
    expect(statValue('Delivered')).toBe('11')
  })

  it('shows the paused-by-system error', async () => {
    signIn()
    renderDashboard(`${base}/${campaignIds.monsoon}`)
    expect(await screen.findByText(/quality rating Meta reports/)).toBeInTheDocument()
    expect(await screen.findAllByText(/per-user marketing limit/)).not.toHaveLength(0)
  })
})

describe('campaign permissions', () => {
  it('keeps viewers read-only', async () => {
    setRole('viewer')
    signIn()
    const { router } = renderDashboard(base)

    expect(await screen.findByRole('link', { name: 'Diwali sale 2026' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Order shipped update' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Monsoon offer' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'New campaign' })).not.toBeInTheDocument()

    await act(() => router.navigate(`${base}/${campaignIds.diwali}`))
    expect(await screen.findByRole('heading', { level: 1, name: 'Diwali sale 2026' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: actionCopy.pause.label })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: actionCopy.cancel.label })).not.toBeInTheDocument()

    await act(() => router.navigate(`${base}/new`))
    expect(await screen.findByRole('heading', { name: "You don't have access to this page" })).toBeInTheDocument()
  })
})
