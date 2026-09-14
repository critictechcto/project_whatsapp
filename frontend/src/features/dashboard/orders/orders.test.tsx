import { act, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { formatNumber } from '../../../lib/format'
import { formatPaise } from '../../../lib/money'
import { dispatch } from '../../../lib/realtime/registry'
import { ids } from '../../../mocks/seed'
import { renderDashboard, signIn } from '../../../test/render'
import { createMockOrder, orderSummary, seededOrder } from './mockState'

const base = `/app/w/${ids.sharmaSweets}/orders`

function orderLink(number: string) {
  return screen.queryByRole('link', { name: number })
}

function summaryValue(label: string) {
  const region = screen.getByRole('region', { name: 'Order summary' })
  return within(region).getByText(label, { selector: 'dt' }).nextElementSibling as HTMLElement
}

describe('orders list', () => {
  it("shows today's summary, the nav link and seeded orders", async () => {
    signIn()
    renderDashboard(base)

    expect(await screen.findByRole('heading', { level: 1, name: 'Orders' }, { timeout: 10_000 })).toBeInTheDocument()
    const nav = screen.getByRole('navigation', { name: 'Workspace' })
    expect(within(nav).getByRole('link', { name: 'Orders' })).toHaveAttribute('href', base)

    const attention = seededOrder('needsAttention').order
    expect(await screen.findByRole('link', { name: attention.number })).toHaveAttribute('href', `${base}/${attention.id}`)

    const summary = orderSummary(ids.sharmaSweets)
    await waitFor(() => expect(summaryValue('Orders today')).toHaveTextContent(formatNumber(summary.today_count)))
    expect(summaryValue('Revenue today')).toHaveTextContent(formatPaise(summary.today_revenue_paise))
    expect(summaryValue('Open')).toHaveTextContent(formatNumber(summary.open_count))
    expect(summaryValue('Needs attention')).toHaveTextContent(formatNumber(summary.needs_attention_count))
    expect(summaryValue('Awaiting payment')).toHaveTextContent(formatNumber(summary.awaiting_payment_count))
    expect(summary.needs_attention_count).toBeGreaterThan(0)
  })

  it('keeps the stage tab and filters in the URL', async () => {
    signIn()
    const { user, router } = renderDashboard(base)
    const attention = seededOrder('needsAttention').order
    const confirmedCod = seededOrder('confirmedCod').order

    expect(await screen.findByRole('link', { name: confirmedCod.number }, { timeout: 10_000 })).toBeInTheDocument()

    await user.click(screen.getByRole('tab', { name: /^Needs attention/ }))
    await waitFor(() => expect(router.state.location.search).toBe('?tab=attention'))
    expect(screen.getByRole('tab', { name: /^Needs attention/ })).toHaveAttribute('aria-selected', 'true')
    await waitFor(() => expect(orderLink(confirmedCod.number)).not.toBeInTheDocument())
    expect(orderLink(attention.number)).toBeInTheDocument()

    await user.click(screen.getByRole('tab', { name: 'Open' }))
    await user.selectOptions(screen.getByLabelText('Payment method'), 'cod')
    await user.selectOptions(screen.getByLabelText('Payment status'), 'cod_pending')
    await waitFor(() => {
      const params = new URLSearchParams(router.state.location.search)
      expect(Object.fromEntries(params)).toEqual({ tab: 'open', method: 'cod', payment: 'cod_pending' })
    })
    expect(await screen.findByRole('link', { name: confirmedCod.number })).toBeInTheDocument()
    await waitFor(() => expect(orderLink(attention.number)).not.toBeInTheDocument())

    await user.type(screen.getByLabelText('Search'), 'SS-0000')
    await waitFor(() => expect(new URLSearchParams(router.state.location.search).get('q')).toBe('SS-0000'))
    expect(await screen.findByRole('heading', { name: 'No orders match these filters' })).toBeInTheDocument()

    await user.click(screen.getAllByRole('button', { name: 'Clear filters' })[0])
    await waitFor(() => expect(router.state.location.search).toBe('?tab=open'))
    expect(await screen.findByRole('link', { name: attention.number })).toBeInTheDocument()
  })

  it('reads filters from the URL on load', async () => {
    signIn()
    renderDashboard(`${base}?tab=closed&method=cod`)
    const deliveredCod = seededOrder('deliveredCod').order

    expect(await screen.findByRole('link', { name: deliveredCod.number }, { timeout: 10_000 })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Closed' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByLabelText('Payment method')).toHaveValue('cod')
    expect(orderLink(seededOrder('shippedCod').order.number)).not.toBeInTheDocument()
    expect(orderLink(seededOrder('cancelledPaid').order.number)).not.toBeInTheDocument()
  })

  it('toasts new orders from realtime and refreshes the list', async () => {
    signIn()
    renderDashboard(base)
    expect(await screen.findByRole('link', { name: seededOrder('needsAttention').order.number }, { timeout: 10_000 })).toBeInTheDocument()

    const record = createMockOrder(ids.sharmaSweets)
    act(() => {
      dispatch({
        v: 1,
        type: 'order.created',
        workspace_id: ids.sharmaSweets,
        data: { order_id: record.order.id, number: record.order.number, status: record.order.status },
      })
    })

    expect(await screen.findByText(`New order ${record.order.number}`)).toBeInTheDocument()
    expect(await screen.findByRole('link', { name: record.order.number })).toHaveAttribute('href', `${base}/${record.order.id}`)
  })
})
