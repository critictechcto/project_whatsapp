import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { formatPaise } from '../../../lib/money'
import { server } from '../../../mocks/node'
import { ids } from '../../../mocks/seed'
import { apiUrl, errorResponse, http } from '../../../mocks/utils'
import { renderDashboard, signIn } from '../../../test/render'
import { filenameFromDisposition } from './api'
import { countDelta, failureLabel, formatNumber, formatRate, rateDelta } from './format'
import { overview } from './mockData'
import { addDays, daysInRange, presetRange, rangeFromSearch, todayIn, validateRange } from './range'

const TZ = 'Asia/Kolkata'
const base = `/app/w/${ids.sharmaSweets}/analytics`
const slow = { timeout: 10_000 }

/** The `<dd>` of a KPI card. */
function kpi(label: string) {
  const region = screen.getByRole('region', { name: 'Key numbers' })
  return within(region).getByText(label, { selector: 'dt' }).nextElementSibling as HTMLElement
}

/** Records the URLs of requests to the analytics API. */
function recordRequests() {
  const urls: URL[] = []
  const listener = ({ request }: { request: Request }) => {
    const url = new URL(request.url)
    if (url.pathname.startsWith('/api/v1/analytics/')) urls.push(url)
  }
  server.events.on('request:start', listener)
  return { urls, stop: () => server.events.removeListener('request:start', listener) }
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('formatting', () => {
  it('formats deltas, with no percent when the previous period is 0', () => {
    expect(countDelta(120, 100)).toEqual({ direction: 'up', text: '20.0%' })
    expect(countDelta(75, 100)).toEqual({ direction: 'down', text: '25.0%' })
    expect(countDelta(100, 100)).toEqual({ direction: 'flat', text: '0.0%' })
    expect(countDelta(12, 0)).toEqual({ direction: 'up', text: null })
    expect(countDelta(0, 0)).toEqual({ direction: 'flat', text: null })
    expect(rateDelta('0.9612', '0.9500')).toEqual({ direction: 'up', text: '1.1 pts' })
    expect(rateDelta('0.9612', null)).toEqual({ direction: 'flat', text: null })
  })

  it('formats rates as percentages with one decimal and counts with Indian grouping', () => {
    expect(formatRate('0.9612')).toBe('96.1%')
    expect(formatRate('1.0000')).toBe('100.0%')
    expect(formatRate(null)).toBe('—')
    expect(formatNumber(1234567)).toBe('12,34,567')
  })

  it('labels common Meta failure codes and shows others raw', () => {
    expect(failureLabel('131026')).toMatch(/undeliverable/i)
    expect(failureLabel('131047')).toMatch(/24 hours/)
    expect(failureLabel('131048')).toMatch(/spam rate limit/i)
    expect(failureLabel('131049')).toMatch(/marketing limit/i)
    expect(failureLabel('131050')).toMatch(/stopped marketing/i)
    expect(failureLabel('131056')).toMatch(/pair rate limit/i)
    expect(failureLabel('130472')).toMatch(/experiment/i)
    expect(failureLabel('131000')).toBe('Error 131000')
    expect(failureLabel('')).toBe('Unknown error')
  })

  it('validates ranges like the API', () => {
    const today = '2026-09-17'
    expect(validateRange({ from: '2026-09-11', to: today }, today)).toBeNull()
    expect(validateRange({ from: addDays(today, -91), to: today }, today)).toBeNull()
    expect(validateRange({ from: addDays(today, -92), to: today }, today)).toMatch(/at most 92 days/)
    expect(validateRange({ from: '2026-09-12', to: '2026-09-10' }, today)).toMatch(/on or before/)
    expect(validateRange({ from: '2026-09-10', to: '2026-09-18' }, today)).toMatch(/future/)
    expect(daysInRange('2026-09-01', '2026-09-30')).toBe(30)
    expect(rangeFromSearch(new URLSearchParams('from=2026-01-01&to=2026-09-17'), today)).toEqual({
      range: presetRange(30, today),
      invalid: true,
    })
    expect(filenameFromDisposition('attachment; filename="upchatz-team-2026-09-01-2026-09-30.csv"')).toBe('upchatz-team-2026-09-01-2026-09-30.csv')
  })
})

describe('analytics page', () => {
  it('renders KPIs from the overview, with orders and revenue', async () => {
    signIn()
    renderDashboard(base)
    const today = todayIn(TZ)
    const expected = overview(ids.sharmaSweets, presetRange(30, today), today, TZ).current

    expect(await screen.findByRole('heading', { level: 1, name: 'Analytics' }, slow)).toBeInTheDocument()
    await screen.findByRole('region', { name: 'Key numbers' }, slow)
    expect(kpi('Messages sent')).toHaveTextContent(formatNumber(expected.messages_sent))
    expect(kpi('Delivery rate')).toHaveTextContent(formatRate(expected.delivery_rate))
    expect(kpi('Read rate')).toHaveTextContent(formatRate(expected.read_rate))
    expect(kpi('Messages received')).toHaveTextContent(formatNumber(expected.messages_received))
    expect(kpi('Orders')).toHaveTextContent(formatNumber(expected.orders!))
    expect(kpi('Revenue')).toHaveTextContent(formatPaise(expected.revenue_paise!, { decimals: 0 }))
    expect(kpi('Messages sent')).toHaveTextContent(/vs previous period/)
  })

  it('shows no percent when the previous period had nothing', async () => {
    signIn()
    const today = todayIn(TZ)
    // The seed covers 90 days, so the 90 days before this range are empty.
    renderDashboard(`${base}?from=${addDays(today, -89)}&to=${today}`)
    await screen.findByRole('region', { name: 'Key numbers' }, slow)
    expect(kpi('Messages sent')).toHaveTextContent('Previous period: 0')
    expect(kpi('Messages sent')).not.toHaveTextContent('%')
    expect(screen.getByLabelText('Date range')).toHaveValue('90')
  })

  it('keeps the range in the URL and refetches when it changes', async () => {
    signIn()
    const requests = recordRequests()
    const { user, router } = renderDashboard(base)
    const today = todayIn(TZ)
    await screen.findByRole('region', { name: 'Key numbers' }, slow)
    expect(screen.getByLabelText('Date range')).toHaveValue('30')

    await user.selectOptions(screen.getByLabelText('Date range'), '7')
    const week = presetRange(7, today)
    await waitFor(() => {
      const params = new URLSearchParams(router.state.location.search)
      expect(params.get('from')).toBe(week.from)
      expect(params.get('to')).toBe(week.to)
    })
    await waitFor(() => {
      const fetched = requests.urls.filter((url) => url.pathname.endsWith('/overview/') && url.searchParams.get('from') === week.from)
      expect(fetched.length).toBeGreaterThan(0)
    }, slow)
    const expected = overview(ids.sharmaSweets, week, today, TZ).current
    await waitFor(() => expect(kpi('Messages sent')).toHaveTextContent(formatNumber(expected.messages_sent)), slow)
    requests.stop()
  })

  it('blocks a custom range longer than 92 days', async () => {
    signIn()
    const { user, router } = renderDashboard(base)
    const today = todayIn(TZ)
    await screen.findByRole('region', { name: 'Key numbers' }, slow)
    const before = router.state.location.search

    await user.selectOptions(screen.getByLabelText('Date range'), 'custom')
    const form = screen.getByRole('form', { name: 'Custom date range' })
    fireEvent.change(within(form).getByLabelText('From'), { target: { value: addDays(today, -100) } })
    fireEvent.change(within(form).getByLabelText('To'), { target: { value: today } })
    await user.click(within(form).getByRole('button', { name: 'Apply' }))

    expect(within(form).getByRole('alert')).toHaveTextContent('Choose a range of at most 92 days.')
    expect(router.state.location.search).toBe(before)

    fireEvent.change(within(form).getByLabelText('From'), { target: { value: addDays(today, -91) } })
    await user.click(within(form).getByRole('button', { name: 'Apply' }))
    await waitFor(() => expect(new URLSearchParams(router.state.location.search).get('from')).toBe(addDays(today, -91)))
  })

  it('shows the upgrade panel when the plan has no analytics', async () => {
    signIn()
    renderDashboard(`/app/w/${ids.kaveriClinic}/analytics`)
    expect(await screen.findByRole('heading', { name: /Analytics is included in the Growth plan/ }, slow)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Compare plans' })).toHaveAttribute('href', `/app/w/${ids.kaveriClinic}/billing/plans`)
    expect(screen.queryByRole('tablist', { name: 'Reports' })).not.toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Key numbers' })).not.toBeInTheDocument()
  })

  it('hides commerce when the commerce report answers 409', async () => {
    let answered = false
    server.use(
      http.untyped.get(apiUrl('/api/v1/analytics/commerce/'), () => {
        answered = true
        return errorResponse(409, 'feature_not_available', 'Selling on WhatsApp is not included in your plan.', { feature: 'commerce' })
      }),
    )
    signIn()
    renderDashboard(`${base}?tab=commerce`)
    await screen.findByRole('region', { name: 'Key numbers' }, slow)
    await waitFor(() => {
      expect(answered).toBe(true)
      expect(screen.queryByRole('tab', { name: 'Commerce' })).not.toBeInTheDocument()
    }, slow)
    expect(screen.getByRole('tab', { name: 'Messages' })).toHaveAttribute('aria-selected', 'true')
  })

  it('shows the commerce tab when commerce is available', async () => {
    signIn()
    const { user } = renderDashboard(base)
    await user.click(await screen.findByRole('tab', { name: 'Commerce' }, slow))
    expect(await screen.findByRole('list', { name: 'Orders by status' }, slow)).toBeInTheDocument()
  })

  it('exports the active report as CSV through the authenticated client', async () => {
    const exported: URL[] = []
    const headers: (string | null)[] = []
    server.use(
      http.untyped.get(apiUrl('/api/v1/analytics/export/'), ({ request }) => {
        exported.push(new URL(request.url))
        headers.push(request.headers.get('Authorization'))
        return new Response('name,email\r\n', {
          headers: { 'Content-Type': 'text/csv; charset=utf-8', 'Content-Disposition': 'attachment; filename="upchatz-team-x.csv"' },
        })
      }),
    )
    const createObjectURL = vi.fn(() => 'blob:analytics')
    const revokeObjectURL = vi.fn()
    Object.assign(URL, { createObjectURL, revokeObjectURL })
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      expect(this.download).toBe('upchatz-team-x.csv')
    })

    signIn()
    const { user } = renderDashboard(`${base}?tab=team`)
    const today = todayIn(TZ)
    await user.click(await screen.findByRole('button', { name: 'Export team as CSV' }, slow))

    await waitFor(() => expect(exported).toHaveLength(1))
    expect(exported[0].searchParams.get('report')).toBe('team')
    expect(exported[0].searchParams.get('from')).toBe(presetRange(30, today).from)
    expect(exported[0].searchParams.get('to')).toBe(today)
    expect(headers[0]).toMatch(/^Bearer /)
    await waitFor(() => expect(click).toHaveBeenCalledTimes(1))
    expect(createObjectURL).toHaveBeenCalledTimes(1)
    Reflect.deleteProperty(URL, 'createObjectURL')
    Reflect.deleteProperty(URL, 'revokeObjectURL')
  })

  it('labels failure reasons and links campaigns to their report', async () => {
    signIn()
    const { user } = renderDashboard(base)
    const reasons = await screen.findByRole('list', { name: 'Failure reasons' }, slow)
    expect(within(reasons).getByText(failureLabel('131026'))).toBeInTheDocument()
    expect(within(reasons).getByText('Code 131026')).toBeInTheDocument()

    await user.click(screen.getByRole('tab', { name: 'Campaigns' }))
    const link = await screen.findByRole('link', { name: 'Monsoon offer' }, slow)
    expect(link).toHaveAttribute('href', `/app/w/${ids.sharmaSweets}/campaigns/6b0e2c4a-8d1f-4e3b-9a5c-7f2d1e0c0003`)
  })

  it('shows an error with retry when a report fails', async () => {
    server.use(
      http.untyped.get(apiUrl('/api/v1/analytics/templates/'), () => errorResponse(404, 'not_found', 'Not found.')),
    )
    signIn()
    const { user } = renderDashboard(`${base}?tab=templates`)
    const alert = await screen.findByRole('alert', {}, slow)
    expect(alert).toHaveTextContent("Couldn't load the templates report")
    server.resetHandlers()
    await user.click(within(alert).getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('table', { name: 'Template performance' }, slow)).toBeInTheDocument()
  })
})
