import { act, fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { SHOP_FINAL_STEP } from '../lib/useShopSequence'
import { SellOnWhatsApp } from './SellOnWhatsApp'

/** Minimal IntersectionObserver whose entries the test fires by hand. */
class FakeIntersectionObserver {
  static instances: FakeIntersectionObserver[] = []
  readonly elements = new Set<Element>()
  constructor(readonly callback: IntersectionObserverCallback) {
    FakeIntersectionObserver.instances.push(this)
  }
  observe(element: Element) {
    this.elements.add(element)
  }
  unobserve(element: Element) {
    this.elements.delete(element)
  }
  disconnect() {
    this.elements.clear()
  }
  takeRecords() {
    return []
  }
}

function setOnScreen(element: Element, isIntersecting: boolean) {
  act(() => {
    for (const observer of FakeIntersectionObserver.instances) {
      if (!observer.elements.has(element)) continue
      observer.callback(
        [{ isIntersecting, target: element } as IntersectionObserverEntry],
        observer as unknown as IntersectionObserver,
      )
    }
  })
}

function stepButton(name: string) {
  return screen.getByRole('button', { name })
}

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
  vi.unstubAllGlobals()
  FakeIntersectionObserver.instances = []
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
    expect(stepButton('Browse the menu')).toHaveAttribute('aria-current', 'step')
    expect(stage(container)).toHaveAttribute('data-shop-autoplay', 'playing')
    // The product card rises on its own layer while its step shows.
    expect(within(stage(container)).getByText('Kaju Katli 250 g').closest('[data-lifted]')).not.toBeNull()
    expect(screen.getByText('Browse the menu').closest('li')!.querySelector('[data-progress]')).toHaveAttribute(
      'data-progress',
      'playing',
    )

    // Each step schedules the next after it renders.
    for (let next = 1; next <= SHOP_FINAL_STEP; next++) {
      act(() => vi.advanceTimersByTime(3000))
      expect(stage(container)).toHaveAttribute('data-shop-step', String(next))
    }
    expect(screen.getByText('Browse the menu').closest('li')).toHaveAttribute('data-state', 'done')
    expect(stepButton('Browse the menu')).not.toHaveAttribute('aria-current')
    expect(within(stage(container)).getByText('Mark shipped')).toBeInTheDocument()
    expect(stage(container)).toHaveAttribute('data-shop-autoplay', 'done')
    // The product card settled back once its step moved on; the ticket stack reached the last status.
    expect(within(stage(container)).getByText('Kaju Katli 250 g').closest('[data-lifted]')).toBeNull()
    expect(stage(container).querySelector('[data-ticket-status="Shipped · Delhivery"]')).toHaveAttribute('data-depth', '0')
    expect(stage(container).querySelector('[data-ticket-status="Paid"]')).toHaveAttribute('data-depth', '1')
  })

  it('jumps to a clicked step and pauses autoplay', () => {
    vi.useFakeTimers()
    mockReducedMotion(false)
    const { container } = render(<SellOnWhatsApp />)
    act(() => vi.advanceTimersByTime(400))
    expect(stage(container)).toHaveAttribute('data-shop-step', '0')

    fireEvent.click(stepButton('Pay by link or cash on delivery'))
    expect(stage(container)).toHaveAttribute('data-shop-step', '3')
    expect(stage(container)).toHaveAttribute('data-shop-autoplay', 'paused')
    expect(within(stage(container)).getByText('Pay ₹540')).toBeInTheDocument()
    expect(within(stage(container)).queryByText('Mark shipped')).not.toBeInTheDocument()
    expect(stepButton('Pay by link or cash on delivery')).toHaveAttribute('aria-current', 'step')
    expect(screen.getAllByRole('button', { current: 'step' })).toHaveLength(1)
    expect(screen.getByText('Build a cart').closest('li')).toHaveAttribute('data-state', 'done')
    const progress = screen.getByText('Pay by link or cash on delivery').closest('li')!.querySelector('[data-progress]')
    expect(progress).toHaveAttribute('data-progress', 'paused')

    // Autoplay stays paused.
    act(() => vi.advanceTimersByTime(20000))
    expect(stage(container)).toHaveAttribute('data-shop-step', '3')

    // Jumping backwards removes the later messages.
    fireEvent.click(stepButton('Build a cart'))
    expect(stage(container)).toHaveAttribute('data-shop-step', '1')
    expect(within(stage(container)).queryByText('Pay ₹540')).not.toBeInTheDocument()
    expect(stage(container).querySelector('[data-ticket-status="Cart"]')).toHaveAttribute('data-depth', '0')
  })

  it('switches steps from the keyboard', async () => {
    mockReducedMotion(false)
    const user = userEvent.setup()
    const { container } = render(<SellOnWhatsApp />)

    // The step buttons are the section's only focusable elements, reached in order.
    await user.tab()
    expect(stepButton('Browse the menu')).toHaveFocus()
    await user.tab()
    await user.tab()
    expect(stepButton('Share an address')).toHaveFocus()
    await user.keyboard('{Enter}')
    expect(stage(container)).toHaveAttribute('data-shop-step', '2')
    expect(stepButton('Share an address')).toHaveAttribute('aria-current', 'step')

    await user.tab()
    await user.keyboard(' ')
    expect(stage(container)).toHaveAttribute('data-shop-step', '3')
    expect(stage(container)).toHaveAttribute('data-shop-autoplay', 'paused')
  })

  it('resumes autoplay after the section leaves the screen and comes back', () => {
    vi.useFakeTimers()
    vi.stubGlobal('IntersectionObserver', FakeIntersectionObserver)
    mockReducedMotion(false)
    const { container } = render(<SellOnWhatsApp />)

    // Nothing plays until the stage is on screen.
    act(() => vi.advanceTimersByTime(5000))
    expect(stage(container)).toHaveAttribute('data-shop-step', '-1')
    setOnScreen(stage(container), true)
    act(() => vi.advanceTimersByTime(400))
    expect(stage(container)).toHaveAttribute('data-shop-step', '0')

    // Scrolling away mid-step keeps the time left on that step.
    act(() => vi.advanceTimersByTime(1000))
    setOnScreen(stage(container), false)
    expect(stage(container)).toHaveAttribute('data-shop-autoplay', 'waiting')
    expect(stage(container)).toHaveAttribute('data-paused')
    act(() => vi.advanceTimersByTime(10000))
    expect(stage(container)).toHaveAttribute('data-shop-step', '0')
    setOnScreen(stage(container), true)
    act(() => vi.advanceTimersByTime(1999))
    expect(stage(container)).toHaveAttribute('data-shop-step', '0')
    act(() => vi.advanceTimersByTime(1))
    expect(stage(container)).toHaveAttribute('data-shop-step', '1')

    // A picked step holds while on screen, then autoplay resumes from it after leaving and returning.
    fireEvent.click(stepButton('Share an address'))
    act(() => vi.advanceTimersByTime(10000))
    expect(stage(container)).toHaveAttribute('data-shop-step', '2')
    setOnScreen(stage(container), false)
    act(() => vi.advanceTimersByTime(10000))
    expect(stage(container)).toHaveAttribute('data-shop-step', '2')
    setOnScreen(stage(container), true)
    expect(stage(container)).toHaveAttribute('data-shop-autoplay', 'playing')
    act(() => vi.advanceTimersByTime(3000))
    expect(stage(container)).toHaveAttribute('data-shop-step', '3')
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
    expect(container.querySelector('[data-lifted]')).toBeNull()
    expect(container.querySelector('.order-ticket-in')).toBeNull()
  })

  it('switches the shown step instantly with reduced motion', () => {
    vi.useFakeTimers()
    mockReducedMotion(true)
    const { container } = render(<SellOnWhatsApp />)

    fireEvent.click(stepButton('Build a cart'))
    expect(stage(container)).toHaveAttribute('data-shop-step', '1')
    expect(stage(container)).toHaveAttribute('data-shop-autoplay', 'done')
    expect(stepButton('Build a cart')).toHaveAttribute('aria-current', 'step')
    const mockup = within(stage(container))
    expect(mockup.getByText('Your cart · 3 items')).toBeInTheDocument()
    expect(mockup.queryByText('Mark shipped')).not.toBeInTheDocument()
    expect(container.querySelector('.chat-pop')).toBeNull()
    expect(container.querySelector('[data-lifted]')).toBeNull()
    expect(container.querySelector('.order-ticket-in')).toBeNull()

    // Nothing plays on from the picked step.
    act(() => vi.advanceTimersByTime(20000))
    expect(stage(container)).toHaveAttribute('data-shop-step', '1')
  })
})
