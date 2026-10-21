import { act, fireEvent, render, screen } from '@testing-library/react'
import { HttpResponse } from 'msw'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { plans } from '../../../config/site'
import { formatINR } from '../../../lib/format'
import { server } from '../../../mocks/node'
import { apiUrl, http } from '../../../mocks/utils'
import { monthsFree, publicPlansUrl } from '../lib/pricing'
import { Pricing } from './Pricing'

function mockReducedMotion(reduce: boolean) {
  vi.spyOn(window, 'matchMedia').mockImplementation(
    (query: string) =>
      ({
        matches: reduce && query.includes('prefers-reduced-motion: reduce'),
        media: query,
        onchange: null,
        addListener: () => {},
        removeListener: () => {},
        addEventListener: () => {},
        removeEventListener: () => {},
        dispatchEvent: () => false,
      }) as MediaQueryList,
  )
}

// Rupee prices the public plans endpoint returns (paise in the API); the billing mocks serve the same.
const monthly = { starter: 999, growth: 2499, pro: 5999 } as Record<string, number>
const annual = (id: string) => monthly[id] * 10
const monthlyPrices = plans.map((plan) => formatINR(monthly[plan.id]))
const annualPerMonth = plans.map((plan) => formatINR(Math.round(annual(plan.id) / 12)))

const publicPlans = (overrides: Record<string, { monthly_price_paise?: number | null; annual_price_paise?: number | null }> = {}) =>
  http.untyped.get(apiUrl('/api/v1/billing/public-plans/'), () =>
    HttpResponse.json({
      gst_rate_percent: 0,
      plans: plans.map((plan) => ({
        id: plan.id,
        name: plan.name,
        monthly_price_paise: monthly[plan.id] * 100,
        annual_price_paise: annual(plan.id) * 100,
        limits: { whatsapp_numbers: 1, members: 2, contacts: 5000 },
        features: [],
        ...overrides[plan.id],
      })),
    }),
  )

function shownPrices() {
  return screen.queryAllByTestId('plan-price').map((price) => price.textContent)
}

async function renderWithPrices() {
  render(<Pricing />)
  await screen.findAllByTestId('plan-price')
}

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
  vi.unstubAllEnvs()
})

describe('Pricing', () => {
  it('shows placeholders until the prices arrive, then the prices from the API', async () => {
    mockReducedMotion(false)
    server.use(publicPlans())
    render(<Pricing />)

    // First render (and the prerendered page): no numbers, a note instead, and no months-free promise.
    expect(shownPrices()).toEqual([])
    expect(screen.getAllByTestId('plan-price-placeholder')).toHaveLength(plans.length)
    expect(screen.getAllByText('Price shown after sign-up')).toHaveLength(plans.length)
    expect(screen.getByRole('button', { name: 'Annual' })).toBeInTheDocument()

    await screen.findAllByTestId('plan-price')
    expect(shownPrices()).toEqual(annualPerMonth)
    expect(screen.queryByTestId('plan-price-placeholder')).not.toBeInTheDocument()
    expect(screen.getByText(`Billed ${formatINR(annual('growth'))} yearly`)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Annual · 2 months free' })).toBeInTheDocument()
  })

  it('checks the prices again when the visitor comes back to the tab', async () => {
    mockReducedMotion(true)
    server.use(publicPlans())
    await renderWithPrices()
    expect(shownPrices()).toContain(formatINR(Math.round(annual('growth') / 12)))

    server.use(publicPlans({ growth: { monthly_price_paise: 1999_00, annual_price_paise: 19990_00 } }))
    const now = Date.now()
    vi.spyOn(Date, 'now').mockReturnValue(now + 31_000)
    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible')
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'))
    })

    await vi.waitFor(() => expect(shownPrices()).toContain(formatINR(Math.round(19990 / 12))))
  })

  it('keeps the placeholders when the prices cannot be loaded', async () => {
    mockReducedMotion(false)
    const requested = vi.fn()
    server.use(
      http.untyped.get(apiUrl('/api/v1/billing/public-plans/'), ({ request }) => {
        requested(request.credentials, request.headers.get('Authorization'))
        return HttpResponse.json({ error: { code: 'upstream_unavailable', message: 'Down', details: null } }, { status: 503 })
      }),
    )
    render(<Pricing />)

    await vi.waitFor(() => expect(requested).toHaveBeenCalled())
    // Public data: no cookies and no auth header.
    expect(requested).toHaveBeenCalledWith('omit', null)
    await act(async () => {})
    expect(shownPrices()).toEqual([])
    expect(screen.getAllByText('Price shown after sign-up')).toHaveLength(plans.length)
    expect(screen.getByRole('button', { name: 'Annual' })).toBeInTheDocument()
  })

  it('says when one billing period of a plan is not available', async () => {
    mockReducedMotion(true)
    server.use(publicPlans({ pro: { annual_price_paise: null } }))
    await renderWithPrices()

    expect(shownPrices()).toEqual(annualPerMonth.slice(0, 2))
    expect(screen.getByText('Not available with annual billing')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Monthly' }))
    expect(shownPrices()).toEqual(monthlyPrices)
  })

  it('uses the fetched GST rate in the description', async () => {
    mockReducedMotion(false)
    server.use(
      http.untyped.get(apiUrl('/api/v1/billing/public-plans/'), () => HttpResponse.json({ gst_rate_percent: 18, plans: [] })),
    )
    render(<Pricing />)
    expect(await screen.findByText(/exclude 18% GST/)).toBeInTheDocument()
  })

  it('rolls to the exact prices when the billing period changes', async () => {
    mockReducedMotion(false)
    server.use(publicPlans())
    await renderWithPrices()
    expect(shownPrices()).toEqual(annualPerMonth)

    vi.useFakeTimers()
    fireEvent.click(screen.getByRole('button', { name: 'Monthly' }))
    act(() => vi.advanceTimersByTime(100))
    // Mid-roll the figure is on its way, and screen readers already have the settled price.
    expect(shownPrices()).not.toEqual(monthlyPrices)
    for (const price of monthlyPrices) expect(screen.getByText(price)).toHaveClass('sr-only')

    act(() => vi.advanceTimersByTime(1000))
    expect(shownPrices()).toEqual(monthlyPrices)

    fireEvent.click(screen.getByRole('button', { name: /Annual/ }))
    act(() => vi.advanceTimersByTime(1000))
    expect(shownPrices()).toEqual(annualPerMonth)
  })

  it('jumps straight to the new price with reduced motion', async () => {
    mockReducedMotion(true)
    server.use(publicPlans())
    await renderWithPrices()

    fireEvent.click(screen.getByRole('button', { name: 'Monthly' }))
    expect(shownPrices()).toEqual(monthlyPrices)
  })

  it('keeps tabular figures off the rupee sign and commas so "₹2,083" has no gaps', async () => {
    mockReducedMotion(false)
    server.use(publicPlans())
    await renderWithPrices()

    for (const price of screen.getAllByTestId('plan-price')) {
      for (const run of price.querySelectorAll('span')) {
        expect(run.classList.contains('tabular-nums')).toBe(/^\d+$/.test(run.textContent ?? ''))
      }
    }
  })

  it('offers plan buttons for the phone swipe row', () => {
    mockReducedMotion(false)
    render(<Pricing />)

    const pager = screen.getByRole('group', { name: 'Show plan' })
    const recommended = plans.find((plan) => plan.recommended)!
    expect(pager.querySelector('[aria-current="true"]')).toHaveTextContent(recommended.name)
  })

  it('uses a magnetic CTA for the recommended plan', () => {
    mockReducedMotion(false)
    render(<Pricing />)

    const ctas = screen.getAllByRole('link', { name: 'Start free trial' })
    expect(ctas).toHaveLength(plans.length)
    const recommended = plans.findIndex((plan) => plan.recommended)
    expect(ctas[recommended].parentElement).toHaveClass('magnetic')
  })
})

describe('pricing source', () => {
  it('reads VITE_PRICING_API_URL, else the API in live mode, else nothing in mock mode', () => {
    expect(publicPlansUrl()).toBe('http://localhost:3000/api/v1/billing/public-plans/')

    vi.stubEnv('VITE_PRICING_API_URL', 'https://app.upchatz.com/')
    expect(publicPlansUrl()).toBe('https://app.upchatz.com/api/v1/billing/public-plans/')

    vi.stubEnv('VITE_PRICING_API_URL', '')
    vi.stubEnv('VITE_API_MODE', 'mock')
    expect(publicPlansUrl()).toBeNull()
  })

  it('computes months free from the two prices', () => {
    expect(monthsFree({ monthly: 2499, annual: 24990 })).toBe(2)
    expect(monthsFree({ monthly: 1000, annual: 9000 })).toBe(3)
    expect(monthsFree({ monthly: 1000, annual: 12000 })).toBeNull()
    expect(monthsFree({ monthly: 1000, annual: null })).toBeNull()
    expect(monthsFree(undefined)).toBeNull()
  })
})
