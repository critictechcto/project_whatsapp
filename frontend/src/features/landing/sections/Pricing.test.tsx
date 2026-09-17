import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ANNUAL_MONTHS_CHARGED, plans } from '../../../config/site'
import { formatINR } from '../../../lib/format'
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

const annualPrice = (monthly: number) => Math.round((monthly * ANNUAL_MONTHS_CHARGED) / 12)

function shownPrices() {
  return screen.getAllByTestId('plan-price').map((price) => price.textContent)
}

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('Pricing', () => {
  it('rolls to the exact prices from site config when the billing period changes', () => {
    vi.useFakeTimers()
    mockReducedMotion(false)
    render(<Pricing />)

    expect(shownPrices()).toEqual(plans.map((plan) => formatINR(annualPrice(plan.monthlyPrice))))

    fireEvent.click(screen.getByRole('button', { name: 'Monthly' }))
    act(() => vi.advanceTimersByTime(100))
    // Mid-roll the figure is on its way, and screen readers already have the settled price.
    expect(shownPrices()).not.toEqual(plans.map((plan) => formatINR(plan.monthlyPrice)))
    for (const plan of plans) expect(screen.getByText(formatINR(plan.monthlyPrice))).toHaveClass('sr-only')

    act(() => vi.advanceTimersByTime(1000))
    expect(shownPrices()).toEqual(plans.map((plan) => formatINR(plan.monthlyPrice)))

    fireEvent.click(screen.getByRole('button', { name: /Annual/ }))
    act(() => vi.advanceTimersByTime(1000))
    expect(shownPrices()).toEqual(plans.map((plan) => formatINR(annualPrice(plan.monthlyPrice))))
  })

  it('jumps straight to the new price with reduced motion', () => {
    mockReducedMotion(true)
    render(<Pricing />)

    fireEvent.click(screen.getByRole('button', { name: 'Monthly' }))
    expect(shownPrices()).toEqual(plans.map((plan) => formatINR(plan.monthlyPrice)))
  })

  it('keeps tabular figures off the rupee sign and commas so "₹2,083" has no gaps', () => {
    mockReducedMotion(false)
    render(<Pricing />)

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
