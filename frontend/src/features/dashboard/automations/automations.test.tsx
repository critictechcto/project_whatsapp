import { act, fireEvent, screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { RoleEnum } from '../../../api/types'
import { db } from '../../../mocks/db'
import { server } from '../../../mocks/node'
import { ids } from '../../../mocks/seed'
import { http, paginate } from '../../../mocks/utils'
import { renderDashboard, signIn } from '../../../test/render'
import { automationState, hoursFor, ruleIds } from './mockState'
import { emptyAction, ruleSchema, ruleToForm } from './ruleForm'

const base = `/app/w/${ids.sharmaSweets}/automations`

function setRole(role: RoleEnum) {
  const membership = db.memberships.find((m) => m.workspace_id === ids.sharmaSweets && m.user_id === ids.demoUser)
  if (!membership) throw new Error('membership missing from seed')
  membership.role = role
}

describe('rule schema', () => {
  it('requires 1 to 5 actions and keywords for the keyword trigger', () => {
    const valid = { ...ruleToForm(null), name: 'Rule', keywords: ['price'], actions: [{ ...emptyAction(), text: 'Hi' }] }
    expect(ruleSchema.safeParse(valid).success).toBe(true)

    const messages = (value: unknown) => {
      const result = ruleSchema.safeParse(value)
      return result.success ? [] : result.error.issues.map((issue) => issue.message)
    }
    expect(messages({ ...valid, actions: [] })).toContain('Add at least one action.')
    expect(messages({ ...valid, actions: Array.from({ length: 6 }, () => valid.actions[0]) })).toContain('A rule can have at most 5 actions.')
    expect(messages({ ...valid, keywords: [] })).toContain('Add at least one keyword for the keyword trigger.')
    expect(messages({ ...valid, trigger: 'new_contact', keywords: [] })).toEqual([])
  })
})

describe('rule editor', () => {
  it('validates keywords and the action limits, then creates the rule', async () => {
    signIn()
    const { user, router } = renderDashboard(`${base}/new`)

    await user.type(await screen.findByLabelText(/^Rule name/), 'Price reply')
    await user.click(screen.getByRole('button', { name: 'Create rule' }))
    expect(await screen.findByText('Add at least one keyword for the keyword trigger.')).toBeInTheDocument()
    expect(screen.getByText('Enter the message to send.')).toBeInTheDocument()

    await user.type(screen.getByLabelText(/^Keywords/), 'price{Enter}')
    expect(screen.getByRole('button', { name: 'Remove keyword price' })).toBeInTheDocument()

    const add = screen.getByRole('button', { name: 'Add action' })
    expect(screen.getByRole('button', { name: 'Remove action 1' })).toBeDisabled()
    for (let i = 0; i < 4; i += 1) await user.click(add)
    expect(screen.getAllByRole('button', { name: /^Remove action/ })).toHaveLength(5)
    expect(add).toBeDisabled()
    for (let i = 5; i > 1; i -= 1) await user.click(screen.getByRole('button', { name: `Remove action ${i}` }))
    expect(add).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Remove action 1' })).toBeDisabled()

    await user.type(screen.getByLabelText(/^Message/), 'Our price list is on its way.')
    await user.click(screen.getByRole('button', { name: 'Create rule' }))

    expect(await screen.findByRole('heading', { level: 1, name: 'Automations' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe(base)
    const created = automationState().rules.find((record) => record.rule.name === 'Price reply')?.rule
    expect(created?.keywords).toEqual(['price'])
    expect(created?.actions).toEqual([{ type: 'send_text', config: { text: 'Our price list is on its way.' } }])
    expect(created?.priority).toBe(4)
  })

  it('requires a collection for Send collection and saves it', async () => {
    const collectionId = 'c011ec70-0000-4000-8000-000000000001'
    server.use(
      http.get('/api/v1/catalog/collections/', ({ request, response }) =>
        response(200).json(
          paginate(request, [
            {
              id: collectionId,
              name: 'Diwali gift boxes',
              description: '',
              position: 0,
              is_active: true,
              product_count: 4,
              created_at: '2026-09-01T10:00:00Z',
              updated_at: '2026-09-01T10:00:00Z',
            },
          ]),
        ),
      ),
    )
    signIn()
    const { user } = renderDashboard(`${base}/new`)

    await user.type(await screen.findByLabelText(/^Rule name/), 'Diwali boxes')
    await user.type(screen.getByLabelText(/^Keywords/), 'diwali{Enter}')
    await user.selectOptions(screen.getByLabelText('Do this'), 'send_collection')
    expect(screen.getByText('Shop actions need your store turned on')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Create rule' }))
    expect(await screen.findByText('Choose a collection.')).toBeInTheDocument()

    const select = screen.getByLabelText(/^Collection/)
    await waitFor(() => expect(select).toBeEnabled())
    await user.selectOptions(select, collectionId)
    await user.click(screen.getByRole('button', { name: 'Create rule' }))

    expect(await screen.findByRole('heading', { level: 1, name: 'Automations' })).toBeInTheDocument()
    const created = automationState().rules.find((record) => record.rule.name === 'Diwali boxes')?.rule
    expect(created?.actions).toEqual([{ type: 'send_collection', config: { collection_id: collectionId } }])
  })

  it('explains the shop menu and catalog actions', async () => {
    signIn()
    const { user } = renderDashboard(`${base}/new`)

    const type = await screen.findByLabelText('Do this', {}, { timeout: 10_000 })
    await user.selectOptions(type, 'send_shop_menu')
    expect(screen.getByText(/Sends your store's welcome menu/)).toBeInTheDocument()
    await user.selectOptions(type, 'send_catalog')
    expect(screen.getByText(/Sends your products to browse/)).toBeInTheDocument()
  })

  it('shows an upgrade message when the plan lacks keyword automations', async () => {
    signIn()
    const { user } = renderDashboard(`/app/w/${ids.kaveriClinic}/automations/new`)

    await user.type(await screen.findByLabelText(/^Rule name/), 'Appointment reply')
    await user.type(screen.getByLabelText(/^Keywords/), 'appointment{Enter}')
    await user.type(screen.getByLabelText(/^Message/), 'Reply with a date to book.')
    await user.click(screen.getByRole('button', { name: 'Create rule' }))

    expect(await screen.findByText("Keyword automations aren't included in your plan")).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'View plans' })).toHaveAttribute('href', `/app/w/${ids.kaveriClinic}/billing`)
  })
})

describe('rules list', () => {
  it('reorders rules and toggles them active', async () => {
    signIn()
    const { user } = renderDashboard(base)

    await user.click(await screen.findByRole('button', { name: 'Move “Welcome message” up' }))
    await waitFor(() => {
      const byId = (id: string) => automationState().rules.find((record) => record.rule.id === id)?.rule.priority
      expect(byId(ruleIds.welcome)).toBe(0)
      expect(byId(ruleIds.price)).toBe(1)
    })

    await user.click(screen.getByRole('switch', { name: 'Active: Diwali order keyword' }))
    await waitFor(() => expect(automationState().rules.find((record) => record.rule.id === ruleIds.diwali)?.rule.is_active).toBe(true))
  })
})

describe('business hours', () => {
  it('saves an overnight slot', async () => {
    signIn()
    const { user } = renderDashboard(`${base}/business-hours`)

    await user.click(await screen.findByRole('switch', { name: 'Open on Sunday' }))
    fireEvent.change(screen.getByLabelText('Sunday slot 1 opens'), { target: { value: '22:00' } })
    fireEvent.change(screen.getByLabelText('Sunday slot 1 closes'), { target: { value: '02:00' } })
    expect(screen.getByText('Overnight: closes 02:00 the next day')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Save business hours' }))
    await waitFor(() => expect(hoursFor(ids.sharmaSweets).schedule).toContainEqual({ day: 6, start: '22:00', end: '02:00' }))
    expect(hoursFor(ids.sharmaSweets).schedule.filter((slot) => slot.day === 0)).toEqual([{ day: 0, start: '10:00', end: '19:00' }])
  })

  it('rejects a slot that opens and closes at the same time', async () => {
    signIn()
    const { user } = renderDashboard(`${base}/business-hours`)

    fireEvent.change(await screen.findByLabelText('Monday slot 1 closes'), { target: { value: '10:00' } })
    await user.click(screen.getByRole('button', { name: 'Save business hours' }))
    expect(await screen.findByText("Opening and closing times can't be the same.")).toBeInTheDocument()
    expect(hoursFor(ids.sharmaSweets).schedule).toContainEqual({ day: 0, start: '10:00', end: '19:00' })
  })

  it('copies Monday to the other weekdays', async () => {
    signIn()
    const { user } = renderDashboard(`${base}/business-hours`)

    fireEvent.change(await screen.findByLabelText('Monday slot 1 opens'), { target: { value: '09:00' } })
    await user.click(screen.getByRole('button', { name: 'Copy Monday to weekdays' }))
    expect(screen.getByLabelText('Friday slot 1 opens')).toHaveValue('09:00')
    expect(screen.getByLabelText('Saturday slot 1 opens')).toHaveValue('10:00')
  })
})

describe('run log', () => {
  it('filters runs and links to the conversation', async () => {
    signIn()
    const { user } = renderDashboard(`${base}/runs`)

    const links = await screen.findAllByRole('link', { name: 'View conversation' })
    expect(links[0]).toHaveAttribute('href', `/app/w/${ids.sharmaSweets}/inbox/c0a1b2c3-d4e5-4f60-8a1b-000000000001`)

    const failed = automationState().runs.filter(({ run }) => run.status === 'failed').length
    await user.selectOptions(screen.getByLabelText('Status'), 'failed')
    await waitFor(() => expect(screen.getAllByRole('link', { name: 'View conversation' })).toHaveLength(failed))
  })
})

describe('automation permissions', () => {
  it('keeps viewers read-only', async () => {
    setRole('viewer')
    signIn()
    const { router } = renderDashboard(base)

    expect(await screen.findByRole('link', { name: 'PRICE keyword reply' })).toBeInTheDocument()
    expect(screen.queryByRole('switch')).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'New rule' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Move/ })).not.toBeInTheDocument()

    await act(() => router.navigate(`${base}/${ruleIds.price}`))
    expect(await screen.findByLabelText(/^Rule name/)).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Save rule' })).not.toBeInTheDocument()

    await act(() => router.navigate(`${base}/business-hours`))
    expect(await screen.findByRole('switch', { name: 'Open on Monday' })).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Save business hours' })).not.toBeInTheDocument()

    await act(() => router.navigate(`${base}/new`))
    expect(await screen.findByRole('heading', { name: "You don't have access to this page" })).toBeInTheDocument()
  })
})
