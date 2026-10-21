import { screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { server } from '../../../mocks/node'
import { ids } from '../../../mocks/seed'
import { http, validationError } from '../../../mocks/utils'
import { renderDashboard, signIn } from '../../../test/render'
import { storeState } from '../store/mockState'
import { bookingPaymentSummary } from './lib/labels'
import { catalogMock } from './mockState'

const base = `/app/w/${ids.sharmaSweets}/catalog`
const LAZY = { timeout: 10_000 }

function seeded(sku: string) {
  return catalogMock().products.find((p) => p.sku === sku)!
}

describe('payment at booking', () => {
  it('validates an advance in percent and rupees and sends it in paise', async () => {
    signIn()
    const { user } = renderDashboard(`${base}/products/new`)
    expect(await screen.findByRole('heading', { level: 1, name: 'Add product' }, LAZY)).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Payment at booking' })).not.toBeInTheDocument()

    await user.click(screen.getByRole('radio', { name: 'Service' }))
    const section = screen.getByRole('region', { name: 'Payment at booking' })
    const select = within(section).getByRole('combobox', { name: 'Payment at booking' })
    expect(select).toHaveValue('store_default')
    expect(within(section).queryByRole('status')).not.toBeInTheDocument()

    await user.type(screen.getByLabelText(/^SKU/), 'HENNA-FEET')
    await user.type(screen.getByLabelText(/^Name/), 'Henna for feet')
    await user.type(screen.getByLabelText(/^Price \(/), '1000')

    await user.selectOptions(select, 'advance')
    expect(within(section).getByText('Buyers pay this online when they book; the rest at the shop.')).toBeInTheDocument()
    expect(within(section).getByRole('radio', { name: '% of price' })).toBeChecked()
    await user.type(within(section).getByLabelText(/^Advance \(%\)/), '120')
    await user.click(screen.getByRole('button', { name: 'Add product' }))
    expect(await within(section).findByText('Enter a whole percentage from 1 to 99.')).toBeInTheDocument()

    await user.click(within(section).getByRole('radio', { name: '₹ amount' }))
    const amount = within(section).getByLabelText(/^Advance \(₹\)/)
    await user.clear(amount)
    await user.type(amount, '1000')
    await user.click(screen.getByRole('button', { name: 'Add product' }))
    expect(await within(section).findByText('The advance must be less than the price.')).toBeInTheDocument()

    await user.clear(amount)
    await user.type(amount, '250.50')
    await user.click(screen.getByRole('button', { name: 'Add product' }))
    await waitFor(() => expect(catalogMock().products.some((p) => p.sku === 'HENNA-FEET')).toBe(true))
    const created = seeded('HENNA-FEET')
    expect(created.booking_payment).toBe('advance')
    expect(created.advance_type).toBe('amount')
    expect(created.advance_value).toBe(25_050)
  })

  it('warns when online payments are not set up, and not once they are', async () => {
    const mehendi = seeded('MEHENDI-BRIDAL')
    signIn()
    const view = renderDashboard(`${base}/products/${mehendi.id}`)
    expect(await screen.findByRole('heading', { level: 1, name: mehendi.name }, LAZY)).toBeInTheDocument()

    const section = screen.getByRole('region', { name: 'Payment at booking' })
    expect(within(section).getByRole('combobox', { name: 'Payment at booking' })).toHaveValue('advance')
    expect(within(section).getByRole('radio', { name: '% of price' })).toBeChecked()
    expect(within(section).getByLabelText(/^Advance \(%\)/)).toHaveValue('20')
    const warning = await within(section).findByRole('status')
    expect(warning).toHaveTextContent("Buyers can't book this service until online payments are set up.")
    expect(within(warning).getByRole('link', { name: 'Store → Payments' })).toHaveAttribute('href', `/app/w/${ids.sharmaSweets}/store/payments`)
    view.unmount()

    storeState(ids.sharmaSweets).account.status = 'verified'
    renderDashboard(`${base}/products/${mehendi.id}`)
    expect(await screen.findByRole('heading', { level: 1, name: mehendi.name }, LAZY)).toBeInTheDocument()
    const again = screen.getByRole('region', { name: 'Payment at booking' })
    await waitFor(() => expect(within(again).getByRole('combobox', { name: 'Payment at booking' })).toHaveValue('advance'))
    expect(within(again).queryByRole('status')).not.toBeInTheDocument()
  })

  it('maps server errors onto the advance field', async () => {
    server.use(
      http.patch('/api/v1/catalog/products/{id}/', ({ response }) =>
        response.untyped(validationError({ advance_value: ['The advance must be less than the price.'] })),
      ),
    )
    const sweets = seeded('SWEETS-CLASS-90')
    signIn()
    const { user } = renderDashboard(`${base}/products/${sweets.id}`)
    expect(await screen.findByRole('heading', { level: 1, name: sweets.name }, LAZY)).toBeInTheDocument()
    const section = screen.getByRole('region', { name: 'Payment at booking' })
    const select = within(section).getByRole('combobox', { name: 'Payment at booking' })
    expect(select).toHaveValue('full')

    await user.selectOptions(select, 'advance')
    await user.type(within(section).getByLabelText(/^Advance \(%\)/), '30')
    await user.click(screen.getByRole('button', { name: 'Save product' }))
    expect(await within(section).findByText('The advance must be less than the price.')).toBeInTheDocument()
  })

  it('relabels availability and max quantity for services only', async () => {
    signIn()
    const { user } = renderDashboard(`${base}/products/new`)
    expect(await screen.findByRole('heading', { level: 1, name: 'Add product' }, LAZY)).toBeInTheDocument()
    const availability = screen.getByRole('combobox', { name: 'Availability' })
    expect(within(availability).getByRole('option', { name: 'In stock' })).toBeInTheDocument()
    expect(screen.getByLabelText(/^Max quantity per order/)).toBeInTheDocument()
    expect(screen.getByText('1 to 99.')).toBeInTheDocument()

    await user.click(screen.getByRole('radio', { name: 'Service' }))
    const bookings = screen.getByRole('combobox', { name: 'Bookings' })
    expect(within(bookings).getByRole('option', { name: 'Open' })).toBeInTheDocument()
    expect(within(bookings).getByRole('option', { name: 'Paused' })).toBeInTheDocument()
    expect(screen.getByLabelText(/^Max people per booking/)).toBeInTheDocument()
    expect(screen.getByText('For example 2 lets a buyer book for two people.')).toBeInTheDocument()
    expect(screen.queryByLabelText(/^Max quantity per order/)).not.toBeInTheDocument()
  })

  it('shows the payment rule on services in the list', async () => {
    expect(bookingPaymentSummary(seeded('MEHENDI-BRIDAL'))).toBe('Advance 20%')
    expect(bookingPaymentSummary(seeded('SWEETS-CLASS-90'))).toBe('Full payment')
    expect(bookingPaymentSummary(seeded('DIWALI-GLOW-60'))).toBeNull()
    expect(bookingPaymentSummary({ ...seeded('MEHENDI-BRIDAL'), advance_type: 'amount', advance_value: 20_000 })).toBe('Advance ₹200')

    signIn()
    renderDashboard(base)
    const table = await screen.findByRole('table', { name: 'Products' }, LAZY)
    const row = (name: string) => within(table).getByRole('link', { name }).closest('tr')!
    await within(table).findByRole('link', { name: seeded('MEHENDI-BRIDAL').name })
    expect(within(row(seeded('MEHENDI-BRIDAL').name)).getByText('Advance 20%')).toBeInTheDocument()
    expect(within(row(seeded('SWEETS-CLASS-90').name)).getByText('Full payment')).toBeInTheDocument()
  })
})
