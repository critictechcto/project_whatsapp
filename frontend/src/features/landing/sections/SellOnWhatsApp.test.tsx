import { act, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { SHOP_FINAL_STEP } from '../lib/useShopSequence'
import { SellOnWhatsApp } from './SellOnWhatsApp'

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

function stage(container: HTMLElement) {
  return container.querySelector<HTMLElement>('[data-shop-step]')!
}

afterEach(() => {
  vi.useRealTimers()
})

describe('Sell on WhatsApp section', () => {
  it('describes the journey and payments in text outside the decorative mockup', () => {
    mockReducedMotion(false)
    const { container } = render(<SellOnWhatsApp />)

    const section = container.querySelector('section#sell')!
    expect(within(section as HTMLElement).getByRole('heading', { level: 2, name: 'Your shop, inside the chat your buyers already use.' })).toBeInTheDocument()
    // Numbered eyebrow: "04 — Sell on WhatsApp".
    expect(section.querySelector('p')).toHaveTextContent(/^04\s*Sell on WhatsApp$/)

    const steps = screen.getAllByRole('heading', { level: 3 }).map((heading) => heading.textContent)
    expect(steps.slice(0, 6)).toEqual([
      'Browse the menu',
      'Build a cart',
      'Share an address',
      'Pay by link or cash on delivery',
      'Get order updates',
      'Manage orders from your phone',
    ])
    expect(screen.getByRole('heading', { name: 'Payments go straight to you' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'No website needed' })).toBeInTheDocument()
    expect(screen.getByText(/your own Razorpay or Cashfree account, so buyers pay you directly/)).toBeInTheDocument()
    expect(screen.getByText(/Meta reviews catalogs and products against its commerce policies/)).toBeInTheDocument()
    expect(screen.getByText(/free under Meta’s current pricing/)).toBeInTheDocument()

    // The phones are decorative.
    const mockup = stage(container).firstElementChild!
    expect(mockup).toHaveAttribute('aria-hidden', 'true')
  })

  it('plays the journey a step at a time', () => {
    vi.useFakeTimers()
    mockReducedMotion(false)
    const { container } = render(<SellOnWhatsApp />)

    expect(stage(container)).toHaveAttribute('data-shop-step', '-1')
    expect(within(stage(container)).queryByText('hi')).not.toBeInTheDocument()

    act(() => vi.advanceTimersByTime(400))
    expect(stage(container)).toHaveAttribute('data-shop-step', '0')
    expect(within(stage(container)).getByText('Kaju Katli 250 g')).toBeInTheDocument()
    expect(within(stage(container)).queryByText('Mark shipped')).not.toBeInTheDocument()
    expect(screen.getByText('Browse the menu').closest('li')).toHaveAttribute('data-state', 'current')

    // Each step schedules the next after it renders.
    for (let next = 1; next <= SHOP_FINAL_STEP; next++) {
      act(() => vi.advanceTimersByTime(3000))
      expect(stage(container)).toHaveAttribute('data-shop-step', String(next))
    }
    expect(screen.getByText('Browse the menu').closest('li')).toHaveAttribute('data-state', 'done')
    expect(within(stage(container)).getByText('Mark shipped')).toBeInTheDocument()
  })

  it('shows the finished journey straight away with reduced motion', () => {
    mockReducedMotion(true)
    const { container } = render(<SellOnWhatsApp />)

    expect(stage(container)).toHaveAttribute('data-shop-step', String(SHOP_FINAL_STEP))
    const mockup = within(stage(container))
    expect(mockup.getByText('Mark shipped')).toBeInTheDocument()
    expect(mockup.getByText('Pay ₹540')).toBeInTheDocument()
    expect(mockup.getByText(/has shipped with Delhivery/)).toBeInTheDocument()
    expect(container.querySelector('.chat-pop')).toBeNull()
    expect(screen.getByText('Manage orders from your phone').closest('li')).toHaveAttribute('data-state', 'current')
    expect(screen.getByText('Browse the menu').closest('li')).toHaveAttribute('data-state', 'done')
  })
})
