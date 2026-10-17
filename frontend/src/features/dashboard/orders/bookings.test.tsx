import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { fromZonedParts } from '../../../lib/datetime'
import { formatPaise } from '../../../lib/money'
import { ids } from '../../../mocks/seed'
import { findDialog, renderDashboard, signIn } from '../../../test/render'
import { availableOrderActions } from './actions'
import { eventTitle } from './labels'
import type { Order } from './api'
import { seededOrder, toOrder } from './mockState'

const ws = `/app/w/${ids.sharmaSweets}`
const slow = { timeout: 10_000 }

async function openOrder(key: string) {
  const record = seededOrder(key)
  signIn()
  const view = renderDashboard(`${ws}/orders/${record.order.id}`)
  expect(await screen.findByRole('heading', { level: 1, name: record.order.number }, slow)).toBeInTheDocument()
  return { ...view, record }
}

function region(name: string) {
  return screen.getByRole('region', { name })
}

function withStatus(order: Order, changes: Partial<Order>): Order {
  return { ...order, ...changes }
}

describe('booking actions', () => {
  const admin = () => true
  const requested = toOrder(seededOrder('bookingRequested'))

  it('offers only booking actions for each status', () => {
    expect(availableOrderActions(requested, admin)).toEqual(['confirm_time', 'cancel'])

    const confirmed = toOrder(seededOrder('bookingConfirmed'))
    expect(availableOrderActions(confirmed, admin)).toEqual(['completed', 'no_show', 'change_time', 'paid_at_shop', 'cancel'])

    const completed = withStatus(confirmed, { status: 'completed', allowed_transitions: [] })
    expect(availableOrderActions(completed, admin)).toEqual(['paid_at_shop'])
    expect(availableOrderActions(withStatus(completed, { payment_status: 'cod_collected' }), admin)).toEqual([])

    const noShow = withStatus(confirmed, { status: 'no_show', allowed_transitions: [] })
    expect(availableOrderActions(noShow, admin)).toEqual([])

    // A booking never offers delivery steps, even if a server listed them.
    const odd = withStatus(confirmed, { allowed_transitions: ['packed', 'shipped', 'delivered', 'completed'] })
    const actions = availableOrderActions(odd, admin)
    expect(actions).not.toContain('packed')
    expect(actions).not.toContain('shipped')
    expect(actions).not.toContain('delivered')
  })
})

describe('booking detail', () => {
  it('shows the booking card in place of the address and tracking, and confirms a time', async () => {
    const { user, record } = await openOrder('bookingRequested')
    const order = record.order

    const booking = region('Booking')
    expect(within(booking).getByText(/Evening \(16:00–20:00\)/)).toBeInTheDocument()
    expect(within(booking).getByText('Not confirmed yet')).toBeInTheDocument()
    expect(within(booking).getByText('Pay at the shop')).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Delivery address' })).not.toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Tracking' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Mark packed' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Mark shipped' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cancel booking' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Confirm time' }))
    const dialog = await findDialog()
    const date = within(dialog).getByLabelText(/^Date/)
    const time = within(dialog).getByLabelText(/^Time/)
    // Starts at the window the buyer asked for.
    expect(date).toHaveValue(order.requested_date)
    expect(time).toHaveValue('16:00')

    fireEvent.change(time, { target: { value: '17:30' } })
    await user.click(within(dialog).getByRole('button', { name: 'Confirm time' }))

    expect(await screen.findByText('Booking confirmed', {}, slow)).toBeInTheDocument()
    expect(record.order.status).toBe('confirmed')
    expect(record.order.appointment_at).toBe(fromZonedParts(order.requested_date!, '17:30', 'Asia/Kolkata'))
    expect(await screen.findByRole('button', { name: 'Mark completed' }, slow)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Change time' })).toBeInTheDocument()
    expect(await within(region('Timeline')).findByText('Appointment time set', {}, slow)).toBeInTheDocument()
  })

  it('shows the offer discount and marks a booking completed, then paid at the shop', async () => {
    const { user, record } = await openOrder('bookingConfirmed')
    const order = record.order

    const items = region('Items')
    expect(within(items).getByText('Offer DIWALI10', { selector: 'dt' }).nextElementSibling).toHaveTextContent(`−${formatPaise(order.discount_paise)}`)
    expect(within(items).queryByText('Shipping', { selector: 'dt' })).not.toBeInTheDocument()
    expect(within(items).getByText('Total', { selector: 'dt' }).nextElementSibling).toHaveTextContent(formatPaise(order.total_paise))
    expect(within(region('Booking')).queryByText('Not confirmed yet')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Mark completed' }))
    let dialog = await findDialog()
    await user.click(within(dialog).getByRole('button', { name: 'Mark completed' }))
    expect(await screen.findByText('Marked completed', {}, slow)).toBeInTheDocument()
    expect(record.order.status).toBe('completed')

    await waitFor(() => expect(screen.queryByRole('button', { name: 'Mark no-show' })).not.toBeInTheDocument(), slow)
    await user.click(await screen.findByRole('button', { name: 'Mark paid at shop' }, slow))
    dialog = await findDialog()
    await user.click(within(dialog).getByRole('button', { name: 'Mark paid' }))
    expect(await screen.findByText('Marked paid at the shop', {}, slow)).toBeInTheDocument()
    expect(record.order.payment_status).toBe('cod_collected')
  })

  it('marks a confirmed booking as a no-show', async () => {
    const { user, record } = await openOrder('bookingConfirmed')
    await user.click(screen.getByRole('button', { name: 'Mark no-show' }))
    const dialog = await findDialog()
    await user.click(within(dialog).getByRole('button', { name: 'Mark no-show' }))
    expect(await screen.findByText('Marked no-show', {}, slow)).toBeInTheDocument()
    expect(record.order.status).toBe('no_show')
  })
})

describe('booking reminders and replies', () => {
  it('shows the evening-before reminder and that the customer will come', async () => {
    const { record } = await openOrder('bookingConfirmed')
    expect(record.order.attendance_confirmed_at).not.toBeNull()

    const booking = region('Booking')
    expect(within(booking).getByText(/\(evening before\)$/)).toBeInTheDocument()
    expect(within(booking).getByText(/Customer confirmed they.ll come/)).toBeInTheDocument()
    expect(within(booking).queryByText('Customer asked to change the time')).not.toBeInTheDocument()

    const timeline = region('Timeline')
    expect(await within(timeline).findByText('Evening-before reminder sent', {}, slow)).toBeInTheDocument()
    expect(within(timeline).getByText("Customer confirmed they'll come")).toBeInTheDocument()
  })

  it('warns when the customer asked to change the time', async () => {
    const { record } = await openOrder('bookingReschedule')
    expect(record.order.reschedule_requested_at).not.toBeNull()

    const booking = region('Booking')
    expect(within(booking).getByText('Customer asked to change the time')).toBeInTheDocument()
    expect(within(booking).getByText(/use Change time to update the booking/)).toBeInTheDocument()
    expect(within(booking).queryByText(/Customer confirmed they.ll come/)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Change time' })).toBeInTheDocument()

    const timeline = region('Timeline')
    expect(await within(timeline).findByText('Customer asked to change the time', {}, slow)).toBeInTheDocument()
  })

  it('labels the reminder sent before the appointment', () => {
    expect(eventTitle({ type: 'reminder_sent', to_status: '', detail: 'Day-before reminder for the appointment at 5 pm' })).toBe('Evening-before reminder sent')
    expect(eventTitle({ type: 'reminder_sent', to_status: '', detail: 'Reminder for the appointment at 5 pm' })).toBe('Reminder sent before the appointment')
  })

  it('explains a confirm-booking conflict', async () => {
    const { user, record } = await openOrder('bookingConfirmed')
    // Someone else completed it meanwhile.
    record.order.status = 'completed'

    await user.click(screen.getByRole('button', { name: 'Change time' }))
    const dialog = await findDialog()
    fireEvent.change(within(dialog).getByLabelText(/^Time/), { target: { value: '18:00' } })
    await user.click(within(dialog).getByRole('button', { name: 'Change time' }))

    expect(await screen.findByText(/This booking is completed now, so it can't be given a time\./, {}, slow)).toBeInTheDocument()
  })
})

describe('orders list kind filter', () => {
  it('filters to bookings and marks them in the list', async () => {
    signIn()
    const { user, router } = renderDashboard(`${ws}/orders`)
    const delivery = seededOrder('confirmedCod').order
    const booking = seededOrder('bookingRequested').order

    expect(await screen.findByRole('link', { name: delivery.number }, slow)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: booking.number })).toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText('Type'), 'booking')
    await waitFor(() => expect(new URLSearchParams(router.state.location.search).get('kind')).toBe('booking'))
    await waitFor(() => {
      expect(screen.queryByRole('link', { name: delivery.number })).not.toBeInTheDocument()
      expect(screen.getByRole('link', { name: booking.number })).toBeInTheDocument()
    }, slow)
    const row = screen.getByRole('link', { name: booking.number }).closest('tr')!
    expect(within(row).getByText('Booking')).toBeInTheDocument()
    expect(within(row).queryByText('Asked to change the time')).not.toBeInTheDocument()

    const reschedule = seededOrder('bookingReschedule').order
    const rescheduleRow = screen.getByRole('link', { name: reschedule.number }).closest('tr')!
    expect(within(rescheduleRow).getByText('Asked to change the time')).toBeInTheDocument()
  })
})
