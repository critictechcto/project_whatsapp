import { act, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { RoleEnum } from '../../../api/types'
import { formatPaise } from '../../../lib/money'
import { dispatch } from '../../../lib/realtime/registry'
import { db } from '../../../mocks/db'
import { ids } from '../../../mocks/seed'
import { findDialog, renderDashboard, signIn } from '../../../test/render'
import { seededOrder } from './mockState'

const ws = `/app/w/${ids.sharmaSweets}`

function setRole(role: RoleEnum) {
  const membership = db.memberships.find((m) => m.workspace_id === ids.sharmaSweets && m.user_id === ids.demoUser)
  if (!membership) throw new Error('membership missing from seed')
  membership.role = role
}

async function openOrder(key: string) {
  const record = seededOrder(key)
  signIn()
  const view = renderDashboard(`${ws}/orders/${record.order.id}`)
  expect(await screen.findByRole('heading', { level: 1, name: record.order.number }, { timeout: 10_000 })).toBeInTheDocument()
  return { ...view, record }
}

function region(name: string) {
  return screen.getByRole('region', { name })
}

describe('order detail', () => {
  it('shows items, customer, address, payment, tracking and a readable timeline', async () => {
    const { record } = await openOrder('shippedTracked')
    const order = record.order

    const items = region('Items')
    for (const item of order.items) expect(within(items).getByText(item.name)).toBeInTheDocument()
    expect(within(items).getByText('Total', { selector: 'dt' }).nextElementSibling).toHaveTextContent(formatPaise(order.total_paise))

    expect(within(region('Customer')).getByRole('link', { name: 'Open conversation' })).toHaveAttribute(
      'href',
      `${ws}/inbox/${order.conversation_id}`,
    )
    expect(within(region('Delivery address')).getByText(order.address!.line1)).toBeInTheDocument()
    expect(within(region('Payment')).getByText('Paid online')).toBeInTheDocument()

    const tracking = region('Tracking')
    expect(within(tracking).getByText('Blue Dart')).toBeInTheDocument()
    expect(within(tracking).getByText(order.awb_number)).toBeInTheDocument()
    expect(within(tracking).getByRole('link', { name: /bluedart\.com/ })).toHaveAttribute('href', order.tracking_url)

    const timeline = region('Timeline')
    expect(await within(timeline).findByText('Moved to Shipped')).toBeInTheDocument()
    expect(within(timeline).getByText(/Map one for this update in/)).toBeInTheDocument()
    expect(within(timeline).getByRole('link', { name: 'Store settings' })).toHaveAttribute('href', `${ws}/store`)
  })

  it('warns about paid orders that need attention and confirms them', async () => {
    const { user, record } = await openOrder('needsAttention')

    expect(screen.getByText('Paid after the checkout expired')).toBeInTheDocument()
    expect(screen.getByText(/refund the buyer in your payment gateway/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Mark refunded' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Mark packed' })).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Confirm order' }))
    const dialog = await findDialog()
    await user.click(within(dialog).getByRole('button', { name: 'Confirm order' }))

    expect(await screen.findByText('Order confirmed')).toBeInTheDocument()
    expect(record.order.status).toBe('confirmed')
    await waitFor(() => expect(screen.queryByText('Paid after the checkout expired')).not.toBeInTheDocument())
    expect(await screen.findByRole('button', { name: 'Mark packed' })).toBeInTheDocument()
  })

  it('validates the ship dialog and ships the order', async () => {
    const { user, record } = await openOrder('confirmedCod')

    await user.click(screen.getByRole('button', { name: 'Mark shipped' }))
    const dialog = await findDialog()
    await user.click(within(dialog).getByRole('button', { name: 'Mark shipped' }))
    expect(await within(dialog).findByText('Enter the courier name.')).toBeInTheDocument()
    expect(within(dialog).getByText('Enter the AWB number.')).toBeInTheDocument()

    await user.type(within(dialog).getByLabelText(/^Courier/), 'Delhivery')
    await user.type(within(dialog).getByLabelText(/^AWB number/), 'DL99887766')
    await user.type(within(dialog).getByLabelText(/^Tracking link/), 'http://track.example.com/DL99887766')
    await user.click(within(dialog).getByRole('button', { name: 'Mark shipped' }))
    expect(await within(dialog).findByText('Enter a full link that starts with https://')).toBeInTheDocument()
    expect(record.order.status).toBe('confirmed')

    await user.clear(within(dialog).getByLabelText(/^Tracking link/))
    await user.type(within(dialog).getByLabelText(/^Tracking link/), 'https://track.example.com/DL99887766')
    const notify = within(dialog).getByRole('checkbox', { name: /Notify the buyer/ })
    expect(notify).toBeChecked()
    await user.click(notify)
    const eventsBefore = record.events.length
    await user.click(within(dialog).getByRole('button', { name: 'Mark shipped' }))

    expect(await screen.findByText('Marked shipped')).toBeInTheDocument()
    expect(record.order).toMatchObject({
      status: 'shipped',
      courier_name: 'Delhivery',
      awb_number: 'DL99887766',
      tracking_url: 'https://track.example.com/DL99887766',
    })
    expect(record.events.slice(eventsBefore).map((event) => event.type)).not.toContain('notification_sent')
    expect(await within(region('Tracking')).findByText('DL99887766')).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: 'Mark delivered' })).toBeInTheDocument()
  })

  it('cancels with a reason and the restock and notify options', async () => {
    const { user, record } = await openOrder('pendingPayment')
    expect(record.order.payment_link?.status).toBe('created')

    await user.click(screen.getByRole('button', { name: 'Cancel order' }))
    const dialog = await findDialog()
    expect(within(dialog).getByText(/If a payment link is still open, it's cancelled too/)).toBeInTheDocument()

    const restock = within(dialog).getByRole('checkbox', { name: /Return items to stock/ })
    const notify = within(dialog).getByRole('checkbox', { name: /Notify the buyer/ })
    expect(restock).toBeChecked()
    expect(notify).toBeChecked()

    const reason = within(dialog).getByLabelText(/^Reason/)
    await user.click(reason)
    await user.paste('x'.repeat(201))
    await user.click(within(dialog).getByRole('button', { name: 'Cancel order' }))
    expect(await within(dialog).findByText('Keep the reason under 200 characters.')).toBeInTheDocument()

    await user.clear(reason)
    await user.type(reason, 'Buyer asked to cancel')
    await user.click(restock)
    const eventsBefore = record.events.length
    await user.click(within(dialog).getByRole('button', { name: 'Cancel order' }))

    expect(await screen.findByText('Order cancelled')).toBeInTheDocument()
    expect(record.order.status).toBe('cancelled')
    expect(record.order.cancel_reason).toBe('Buyer asked to cancel')
    expect(record.order.payment_link?.status).toBe('cancelled')
    const added = record.events.slice(eventsBefore).map((event) => event.type)
    expect(added).not.toContain('stock_released')
    expect(added).toContain('notification_sent')
    // The reason shows in the cancelled notice and in the timeline.
    expect(await screen.findAllByText('Buyer asked to cancel')).toHaveLength(2)
  })

  it('shows only the actions allowed for the status and role', async () => {
    const { unmount } = await openOrder('packedCod')
    expect(screen.getByRole('button', { name: 'Mark shipped' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cancel order' })).toBeInTheDocument()
    for (const name of ['Mark packed', 'Mark delivered', 'Confirm order', 'Mark COD collected', 'Mark refunded']) {
      expect(screen.queryByRole('button', { name })).not.toBeInTheDocument()
    }
    unmount()

    const delivered = await openOrder('deliveredCod')
    expect(screen.getByRole('button', { name: 'Mark COD collected' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Cancel order' })).not.toBeInTheDocument()
    delivered.unmount()

    const owner = await openOrder('cancelledPaid')
    expect(screen.getByRole('button', { name: 'Mark refunded' })).toBeInTheDocument()
    owner.unmount()

    setRole('agent')
    await openOrder('cancelledPaid')
    expect(screen.queryByRole('button', { name: 'Mark refunded' })).not.toBeInTheDocument()
  })

  it('explains a 409 invalid transition and refreshes the order', async () => {
    const { user, record } = await openOrder('confirmedCod')
    await user.click(screen.getByRole('button', { name: 'Mark packed' }))
    const dialog = await findDialog()

    // Someone else delivered it in the meantime.
    record.order.status = 'delivered'
    await user.click(within(dialog).getByRole('button', { name: 'Mark packed' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent("This order is delivered now, so it can't be moved to packed. Its status can't be changed any more.")
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Mark packed' })).not.toBeInTheDocument())
  })

  it('refreshes when a realtime order.updated arrives', async () => {
    const { record } = await openOrder('confirmedCod')
    expect(screen.getByRole('button', { name: 'Mark packed' })).toBeInTheDocument()

    record.order.status = 'packed'
    act(() => {
      dispatch({
        v: 1,
        type: 'order.updated',
        workspace_id: ids.sharmaSweets,
        data: { order_id: record.order.id, status: 'packed', payment_status: record.order.payment_status },
      })
    })

    await waitFor(() => expect(screen.queryByRole('button', { name: 'Mark packed' })).not.toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Mark shipped' })).toBeInTheDocument()
  })
})
