import { screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { RoleEnum } from '../../../api/types'
import { db } from '../../../mocks/db'
import { ids, indianName } from '../../../mocks/seed'
import { fill, findDialog, renderDashboard, signIn } from '../../../test/render'
import { discountSummary, normalisePhone } from './format'
import { claimIds, offerIds, offerState } from './mockState'
import { formToBody, offerSchema, offerToForm } from './offerForm'

const base = `/app/w/${ids.sharmaSweets}/offers`

function setRole(role: RoleEnum) {
  const membership = db.memberships.find((m) => m.workspace_id === ids.sharmaSweets && m.user_id === ids.demoUser)
  if (!membership) throw new Error('membership missing from seed')
  membership.role = role
}

describe('offer helpers', () => {
  it('summarises discounts and normalises phone numbers', () => {
    expect(discountSummary({ discount_type: 'percent', discount_value: 15, max_discount_paise: 30_000, min_order_paise: 50_000 })).toBe(
      '15% off (up to ₹300) on ₹500+',
    )
    expect(discountSummary({ discount_type: 'amount', discount_value: 10_000, max_discount_paise: null, min_order_paise: 0 })).toBe('₹100 off')
    expect(discountSummary({ discount_type: 'none', discount_value: 0, max_discount_paise: null, min_order_paise: 0 })).toBe('Message only')
    expect(normalisePhone('98765 43210')).toBe('+919876543210')
    expect(normalisePhone('+44 7700 900123')).toBe('+447700900123')
    expect(normalisePhone('12345')).toBeNull()
  })

  it('validates the form and builds the API body in paise', () => {
    const values = { ...offerToForm(null, 'Asia/Kolkata'), code: 'HOLI', title: 'Holi', reply_text: 'Happy Holi', percent: '10', max_discount: '250' }
    expect(offerSchema.safeParse(values).success).toBe(true)
    expect(offerSchema.safeParse({ ...values, percent: '95' }).success).toBe(false)
    expect(offerSchema.safeParse({ ...values, starts_on: '2026-11-10', ends_on: '2026-11-01' }).success).toBe(false)
    const body = formToBody({ ...values, starts_on: '2026-11-01', ends_on: '2026-11-01', min_order: '499.50' }, 'Asia/Kolkata')
    expect(body).toMatchObject({ code: 'HOLI', discount_type: 'percent', discount_value: 10, max_discount_paise: 25_000, min_order_paise: 49_950 })
    expect(body.starts_at).toBe('2026-10-31T18:30:00.000Z')
    expect(body.ends_at).toBe('2026-11-01T18:29:59.999Z')
  })
})

describe('offer codes list', () => {
  it('lists codes with their counters and toggles a code off', async () => {
    signIn()
    const { user } = renderDashboard(base)

    const table = within(await screen.findByRole('table', { name: 'Offer codes' }))
    const diwali = (await table.findByRole('link', { name: 'DIWALI' })).closest('tr')!
    expect(within(diwali).getByText('15% off (up to ₹300) on ₹500+')).toBeInTheDocument()
    expect(within(diwali).getByText('6')).toBeInTheDocument()
    expect(within(diwali).getByText('2')).toBeInTheDocument()
    expect(table.getByRole('link', { name: 'KAJU100' })).toBeInTheDocument()

    await user.click(within(diwali).getByRole('switch', { name: 'Active: DIWALI' }))
    await waitFor(() => expect(offerState().codes.find((code) => code.id === offerIds.diwali)?.is_active).toBe(false))
  })

  it('shows the upgrade panel when the plan lacks commerce', async () => {
    signIn()
    renderDashboard(`/app/w/${ids.kaveriClinic}/offers`)
    expect(await screen.findByRole('heading', { name: 'Offer codes come with selling on WhatsApp' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Redeem at counter' })).not.toBeInTheDocument()
  })
})

describe('offer code editor', () => {
  it('validates, maps server errors and creates a code', async () => {
    signIn()
    const { user, router } = renderDashboard(`${base}/new`)

    const code = await screen.findByLabelText(/^Code\*?$/)
    await user.click(screen.getByRole('button', { name: 'Create code' }))
    expect(await screen.findByText('Enter a code.')).toBeInTheDocument()
    expect(screen.getByText('Enter a title.')).toBeInTheDocument()
    expect(screen.getByText('Enter the reply customers get.')).toBeInTheDocument()
    expect(screen.getByText('Enter a whole percent from 1 to 90.')).toBeInTheDocument()

    await user.type(code, 'menu')
    expect(code).toHaveValue('MENU')
    await user.type(screen.getByLabelText(/^Title/), 'Holi offer')
    await fill(user, screen.getByLabelText(/^Reply message/), 'Happy Holi! *10% off* today.')
    expect(within(screen.getByRole('complementary', { name: 'Reply preview' })).getByText('10% off')).toBeInTheDocument()
    await user.type(screen.getByLabelText(/^Discount percent/), '10')
    await user.click(screen.getByRole('button', { name: 'Create code' }))

    // The mock rejects shop keywords, like the backend.
    expect(await screen.findByText('MENU is already a shop or opt-out keyword. Choose another code.')).toBeInTheDocument()

    await user.clear(code)
    await user.type(code, 'holi-10')
    await user.click(screen.getByRole('button', { name: 'Create code' }))

    expect(await screen.findByRole('heading', { level: 1, name: 'HOLI-10' })).toBeInTheDocument()
    const created = offerState().codes.find((item) => item.code === 'HOLI-10')
    expect(created).toMatchObject({ discount_type: 'percent', discount_value: 10, title: 'Holi offer', is_active: true })
    expect(router.state.location.pathname).toBe(`${base}/${created?.id}`)
  })

  it('applies a code to chosen products or services', async () => {
    signIn()
    const { user } = renderDashboard(`${base}/new`)

    await user.type(await screen.findByLabelText(/^Code\*?$/), 'GLOW')
    await user.type(screen.getByLabelText(/^Title/), 'Glow facial offer')
    await fill(user, screen.getByLabelText(/^Reply message/), '20% off the Diwali Glow facial.')
    await user.type(screen.getByLabelText(/^Discount percent/), '20')
    await user.selectOptions(screen.getByLabelText('Applies to'), 'items')
    await user.click(screen.getByRole('button', { name: 'Create code' }))
    expect(await screen.findByText('Choose at least one product or service.')).toBeInTheDocument()

    const list = within(await screen.findByRole('list', { name: 'Products and services' }))
    await user.type(screen.getByRole('textbox', { name: 'Search products and services' }), 'glow')
    await user.click(list.getByRole('checkbox', { name: /Diwali Glow facial/ }))
    expect(screen.getByText('1 chosen')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Create code' }))

    expect(await screen.findByRole('heading', { level: 1, name: 'GLOW' })).toBeInTheDocument()
    expect(screen.getByText(/On Diwali Glow facial/)).toBeInTheDocument()
    const created = offerState().codes.find((item) => item.code === 'GLOW')
    expect(created?.applies_to).toBe('items')
    expect(created?.product_ids).toHaveLength(1)
  })

  it('suggests turning a used code off instead of deleting it', async () => {
    signIn()
    const { user } = renderDashboard(`${base}/${offerIds.diwali}/edit`)

    await user.click(await screen.findByRole('button', { name: 'Delete' }))
    const dialog = await findDialog()
    await user.click(within(dialog).getByRole('button', { name: 'Delete code' }))
    expect(await screen.findByText("DIWALI has been used, so it can't be deleted")).toBeInTheDocument()
    expect(offerState().codes.some((code) => code.id === offerIds.diwali)).toBe(true)
  })
})

describe('offer code detail', () => {
  it('shows stats and filters claims by status and phone', async () => {
    signIn()
    const { user } = renderDashboard(`${base}/${offerIds.diwali}`)

    const stats = await screen.findByRole('region', { name: 'Results' })
    const tile = (label: string) => within(stats).getByText(label).closest('div')!
    await waitFor(() => expect(within(tile('People sent')).getByText('6')).toBeInTheDocument())
    expect(within(tile('From ads')).getByText('3')).toBeInTheDocument()
    expect(within(tile('Redeemed')).getByText('2')).toBeInTheDocument()
    expect(within(tile('Revenue')).getByText('₹3,470')).toBeInTheDocument()

    const table = within(await screen.findByRole('table', { name: 'Claims of DIWALI' }))
    expect(await table.findByText(indianName(6))).toBeInTheDocument()
    expect(table.getByRole('link', { name: 'SS-1042' })).toHaveAttribute('href', `/app/w/${ids.sharmaSweets}/orders/7d0a4e3c-9f6b-4a1c-a5e8-3b4c5d6e7f01`)
    expect(table.getAllByText('Diwali sweets, 15% off on WhatsApp')).toHaveLength(2)

    await user.selectOptions(screen.getByLabelText('Status'), 'redeemed')
    await waitFor(() => expect(within(screen.getByRole('table', { name: 'Claims of DIWALI' })).getAllByRole('row')).toHaveLength(3))
    expect(within(screen.getByRole('table', { name: 'Claims of DIWALI' })).queryByText(indianName(6))).not.toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText('Status'), '')
    const phone = offerState().claims.find((claim) => claim.id === claimIds.fromAd)!.contact.phone_e164
    await user.type(screen.getByLabelText('Search by phone'), phone.slice(3, 10))
    await waitFor(() => expect(within(screen.getByRole('table', { name: 'Claims of DIWALI' })).getAllByRole('row')).toHaveLength(2))
    expect(within(screen.getByRole('table', { name: 'Claims of DIWALI' })).getByText(indianName(5))).toBeInTheDocument()
  })

  it('redeems an open claim with a bill amount', async () => {
    signIn()
    const { user } = renderDashboard(`${base}/${offerIds.diwali}`)

    const table = within(await screen.findByRole('table', { name: 'Claims of DIWALI' }))
    await user.click(await table.findByRole('button', { name: `Redeem for ${indianName(5)}` }))
    const dialog = await findDialog({ name: 'Redeem DIWALI' })
    await user.type(within(dialog).getByLabelText(/^Bill amount/), '12x')
    await user.click(within(dialog).getByRole('button', { name: 'Redeem' }))
    expect(await within(dialog).findByText('Enter the bill in rupees, like 1450.')).toBeInTheDocument()

    await user.clear(within(dialog).getByLabelText(/^Bill amount/))
    await user.type(within(dialog).getByLabelText(/^Bill amount/), '1,200')
    await user.click(within(dialog).getByRole('button', { name: 'Redeem' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(offerState().claims.find((claim) => claim.id === claimIds.fromAd)).toMatchObject({ status: 'redeemed', bill_paise: 120_000, discount_paise: 18_000 })
  })
})

describe('redeem at counter', () => {
  it('records a walk-in and shows offer_unavailable inline', async () => {
    signIn()
    const { user } = renderDashboard(base)

    await user.click(await screen.findByRole('button', { name: 'Redeem at counter' }))
    let dialog = await findDialog({ name: 'Redeem at counter' })
    await user.type(within(dialog).getByLabelText(/^Offer code/), 'namaste')
    expect(within(dialog).getByLabelText(/^Offer code/)).toHaveValue('NAMASTE')
    await user.type(within(dialog).getByLabelText(/^Customer's WhatsApp number/), '98111 22233')
    await user.click(within(dialog).getByRole('button', { name: 'Redeem' }))
    expect(await within(dialog).findByRole('alert')).toHaveTextContent("NAMASTE can't be used right now")

    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    await user.click(screen.getByRole('button', { name: 'Redeem at counter' }))
    dialog = await findDialog({ name: 'Redeem at counter' })
    await user.type(within(dialog).getByLabelText(/^Offer code/), 'diwali')
    await user.type(within(dialog).getByLabelText(/^Customer's WhatsApp number/), '98111 22233')
    await user.type(within(dialog).getByLabelText(/^Bill amount/), '1000')
    await user.click(within(dialog).getByRole('button', { name: 'Redeem' }))

    expect(await screen.findByText('Offer redeemed')).toBeInTheDocument()
    const claim = offerState().claims.find((item) => item.contact.phone_e164 === '+919811122233')
    expect(claim).toMatchObject({ offer: offerIds.diwali, status: 'redeemed', bill_paise: 100_000, discount_paise: 15_000 })
  })
})

describe('roles', () => {
  it('lets agents redeem but not edit', async () => {
    setRole('agent')
    signIn()
    const { user } = renderDashboard(`${base}/${offerIds.diwali}`)

    const table = within(await screen.findByRole('table', { name: 'Claims of DIWALI' }))
    expect(await table.findByRole('button', { name: `Redeem for ${indianName(5)}` })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Redeem at counter' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Edit' })).not.toBeInTheDocument()

    await user.click(screen.getAllByRole('link', { name: 'Offers' })[0])
    const list = within(await screen.findByRole('table', { name: 'Offer codes' }))
    expect(await list.findByRole('link', { name: 'DIWALI' })).toBeInTheDocument()
    expect(list.queryByRole('switch')).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'New code' })).not.toBeInTheDocument()
  })

  it('blocks the editor for agents', async () => {
    setRole('agent')
    signIn()
    renderDashboard(`${base}/new`)
    expect(await screen.findByText("You don't have access to this page")).toBeInTheDocument()
  })

  it('keeps viewers read-only', async () => {
    setRole('viewer')
    signIn()
    renderDashboard(`${base}/${offerIds.diwali}`)

    const table = within(await screen.findByRole('table', { name: 'Claims of DIWALI' }))
    expect(await table.findByText(indianName(5))).toBeInTheDocument()
    expect(table.queryByRole('button', { name: /^Redeem/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Redeem at counter' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Edit' })).not.toBeInTheDocument()
  })
})
