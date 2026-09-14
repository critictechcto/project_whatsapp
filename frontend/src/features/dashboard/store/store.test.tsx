import { screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { Role } from '../../../lib/roles'
import { db } from '../../../mocks/db'
import { ids } from '../../../mocks/seed'
import { renderDashboard, signIn } from '../../../test/render'
import { STARTER_TEMPLATE_NAMES, storeState } from './mockState'
import { formToPatch, settingsSchema, settingsToForm } from './settingsForm'

const storePath = `/app/w/${ids.sharmaSweets}/store`
const lazy = { timeout: 10_000 }

function setRole(role: Role) {
  const membership = db.memberships.find((m) => m.workspace_id === ids.sharmaSweets && m.user_id === ids.demoUser)
  if (!membership) throw new Error('seed membership missing')
  membership.role = role
}

describe('store access', () => {
  it('shows Store in the nav and the setup checklist for admins', async () => {
    setRole('admin')
    signIn()
    renderDashboard(storePath)

    expect(await screen.findByRole('heading', { level: 1, name: 'Store' }, lazy)).toBeInTheDocument()
    const nav = screen.getByRole('navigation', { name: 'Workspace' })
    expect(within(nav).getByRole('link', { name: 'Store' })).toHaveAttribute('href', storePath)
    const sections = screen.getByRole('navigation', { name: 'Store sections' })
    expect(within(sections).getAllByRole('link').map((link) => link.textContent)).toEqual(['Setup', 'Settings', 'Payments', 'Alerts', 'Notifications'])
  })

  it('hides Store from agents and blocks every store route', async () => {
    setRole('agent')
    signIn()
    renderDashboard(`${storePath}/payments`)

    expect(await screen.findByRole('heading', { name: "You don't have access to this page" }, lazy)).toBeInTheDocument()
    const nav = screen.getByRole('navigation', { name: 'Workspace' })
    expect(within(nav).queryByRole('link', { name: 'Store' })).not.toBeInTheDocument()
    expect(within(nav).getByRole('link', { name: 'Orders' })).toBeInTheDocument()
    expect(within(nav).getByRole('link', { name: 'Catalog' })).toBeInTheDocument()
  })
})

describe('setup checklist', () => {
  it('lists the six steps with links, the store link and the Meta charges note', async () => {
    signIn()
    renderDashboard(storePath)

    const steps = await screen.findByRole('list', { name: 'Store setup steps' }, lazy)
    expect(within(steps).getAllByRole('listitem')).toHaveLength(6)
    expect(screen.getByText('4 of 6 steps done')).toBeInTheDocument()
    expect(within(steps).getByText('+91 98290 11223 is connected.')).toBeInTheDocument()
    expect(within(steps).getByText('1 of 6 order updates have a template.')).toBeInTheDocument()
    expect(within(steps).getByRole('link', { name: 'Choose templates' })).toHaveAttribute('href', `${storePath}/notifications`)
    expect(within(steps).getByRole('link', { name: 'Add products' })).toHaveAttribute('href', `/app/w/${ids.sharmaSweets}/catalog`)

    expect(await screen.findByRole('textbox', { name: 'Store link' })).toHaveValue('https://wa.me/919829011223?text=Hi')
    expect(screen.getByRole('link', { name: 'Open in WhatsApp' })).toHaveAttribute('href', 'https://wa.me/919829011223?text=Hi')
    expect(screen.getByRole('button', { name: 'Copy store link' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open WhatsApp Manager' })).toHaveAttribute('href', 'https://business.facebook.com/wa/manage/home/')
    expect(screen.getByText(/which Meta doesn't charge for under its current pricing/)).toBeInTheDocument()
  })
})

describe('store settings', () => {
  it('validates the form in rupees and pincodes', () => {
    const values = settingsToForm(storeState(ids.sharmaSweets).settings)
    expect(values.shipping_fee).toBe('60')
    const messages = (patch: Partial<typeof values>) => {
      const result = settingsSchema.safeParse({ ...values, ...patch })
      return result.success ? [] : result.error.issues.map((issue) => issue.message)
    }
    expect(messages({})).toEqual([])
    expect(messages({ order_prefix: 'S1' })).toContain('Use 2 to 5 capital letters, like SS.')
    expect(messages({ shipping_fee: '60.555' })).toContain('Enter an amount in rupees, like 60 or 99.50.')
    expect(formToPatch({ ...values, shipping_fee: '75.50', free_shipping_above: '' })).toMatchObject({
      shipping_fee_paise: 7550,
      free_shipping_above_paise: null,
    })
  })

  it('previews the welcome menu, rejects bad input and saves', async () => {
    signIn()
    const { user } = renderDashboard(`${storePath}/settings`)

    const welcome = await screen.findByLabelText(/^Welcome message/, {}, lazy)
    const preview = screen.getByRole('group', { name: 'Welcome menu preview' })
    expect(within(preview).getByText('Shop now')).toBeInTheDocument()
    expect(within(preview).getByText('My orders')).toBeInTheDocument()
    expect(within(preview).getByText('Talk to us')).toBeInTheDocument()
    expect(within(preview).getByText('Powered by UpChatz')).toBeInTheDocument()

    await user.clear(welcome)
    await user.type(welcome, 'Hello from Jaipur')
    expect(within(preview).getByText('Hello from Jaipur')).toBeInTheDocument()
    await user.click(screen.getByRole('switch', { name: /Powered by UpChatz/ }))
    expect(within(preview).queryByText('Powered by UpChatz')).not.toBeInTheDocument()

    const pincodes = screen.getByRole('textbox', { name: /^Delivery pincodes/ })
    await user.type(pincodes, '30200{Enter}')
    expect(screen.getByText('“30200” isn\'t a 6-digit pincode.')).toBeInTheDocument()
    await user.clear(pincodes)
    await user.type(pincodes, '302020{Enter}')
    expect(screen.getByRole('button', { name: 'Remove pincode 302020' })).toBeInTheDocument()

    const prefix = screen.getByLabelText(/^Order number prefix/)
    await user.clear(prefix)
    await user.type(prefix, 'S1')
    const shipping = screen.getByLabelText(/^Shipping fee/)
    await user.clear(shipping)
    await user.type(shipping, '75')
    await user.click(screen.getByRole('button', { name: 'Save settings' }))
    expect(await screen.findByText('Use 2 to 5 capital letters, like SS.')).toBeInTheDocument()

    await user.clear(prefix)
    await user.type(prefix, 'sws')
    await user.click(screen.getByRole('button', { name: 'Save settings' }))
    await waitFor(() => expect(storeState(ids.sharmaSweets).settings.order_prefix).toBe('SWS'))
    const saved = storeState(ids.sharmaSweets).settings
    expect(saved.shipping_fee_paise).toBe(7500)
    expect(saved.welcome_message).toBe('Hello from Jaipur')
    expect(saved.powered_by_footer).toBe(false)
    expect(saved.serviceable_pincodes).toEqual(['302001', '302004', '302017', '302020'])
  })

  it('explains why the store cannot be turned on', async () => {
    signIn()
    const { user } = renderDashboard(`/app/w/${ids.kaveriClinic}/store/settings`)

    await user.click(await screen.findByRole('switch', { name: /^Store is on/ }, lazy))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent("The store can't be turned on yet")
    expect(alert).toHaveTextContent('To turn on the store, connect a WhatsApp number and add at least one active product.')
    expect(storeState(ids.kaveriClinic).settings.enabled).toBe(false)
  })

  it('shows the catalog error when native catalog mode is not available', async () => {
    signIn()
    const { user } = renderDashboard(`${storePath}/settings`)

    await user.click(await screen.findByRole('radio', { name: /^WhatsApp catalog/ }, lazy))
    await user.click(screen.getByRole('button', { name: 'Save settings' }))
    expect(await screen.findByText('Connect a Meta catalog on the Catalog page before choosing native catalog mode.')).toBeInTheDocument()
    expect(storeState(ids.sharmaSweets).settings.shop_mode).toBe('bot')
  })
})

describe('notifications', () => {
  it('creates starter templates and reports existing ones', async () => {
    signIn()
    const { user } = renderDashboard(`${storePath}/notifications`)

    await user.click(await screen.findByRole('button', { name: 'Create starter templates' }, lazy))
    const created = await screen.findByRole('list', { name: 'Created templates' })
    expect(within(created).getAllByRole('listitem').map((item) => item.textContent)).toEqual([...STARTER_TEMPLATE_NAMES])

    await user.click(screen.getByRole('button', { name: 'Create starter templates' }))
    const existing = await screen.findByRole('list', { name: 'Existing templates' })
    expect(within(existing).getAllByRole('listitem')).toHaveLength(STARTER_TEMPLATE_NAMES.length)
    expect(screen.getByText('Nothing new; you already have them all.')).toBeInTheDocument()
  })

  it('clears a template mapping and saves', async () => {
    signIn()
    const { user } = renderDashboard(`${storePath}/notifications`)

    await user.click(await screen.findByRole('button', { name: 'Clear template for Shipped' }, lazy))
    await user.click(screen.getByRole('button', { name: 'Save templates' }))
    await waitFor(() => expect(storeState(ids.sharmaSweets).settings.notification_templates.shipped).toBeNull())
  })
})
