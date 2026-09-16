import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Tabs, type TabItem } from './Tabs'

const items: TabItem[] = [
  { id: 'campaigns', label: 'Campaigns', content: <p>Campaign panel</p> },
  { id: 'inbox', label: 'Inbox', content: <p>Inbox panel</p> },
  { id: 'analytics', label: 'Analytics', content: <p>Analytics panel</p> },
]

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

function selectedTab() {
  return screen.getAllByRole('tab').find((tab) => tab.getAttribute('aria-selected') === 'true')!
}

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('Tabs', () => {
  it('advances on its own and stops for good once a tab is picked', () => {
    mockReducedMotion(false)
    const { container } = render(<Tabs items={items} label="Features" autoAdvanceMs={1000} />)

    expect(selectedTab()).toHaveTextContent('Campaigns')
    expect(container.querySelector('.tabs-progress')).not.toBeNull()

    act(() => vi.advanceTimersByTime(1000))
    expect(selectedTab()).toHaveTextContent('Inbox')
    expect(screen.getByRole('tabpanel')).toHaveTextContent('Inbox panel')

    fireEvent.click(screen.getByRole('tab', { name: 'Analytics' }))
    expect(selectedTab()).toHaveTextContent('Analytics')
    expect(container.querySelector('.tabs-progress')).toBeNull()

    act(() => vi.advanceTimersByTime(5000))
    expect(selectedTab()).toHaveTextContent('Analytics')
  })

  it('pauses while focus is inside and resumes with the time that was left', () => {
    mockReducedMotion(false)
    render(
      <>
        <Tabs items={items} label="Features" autoAdvanceMs={1000} />
        <button type="button">Outside</button>
      </>,
    )

    act(() => vi.advanceTimersByTime(600))
    act(() => screen.getByRole('tabpanel').focus())
    act(() => vi.advanceTimersByTime(3000))
    expect(selectedTab()).toHaveTextContent('Campaigns')

    act(() => screen.getByRole('button', { name: 'Outside' }).focus())
    act(() => vi.advanceTimersByTime(399))
    expect(selectedTab()).toHaveTextContent('Campaigns')
    act(() => vi.advanceTimersByTime(1))
    expect(selectedTab()).toHaveTextContent('Inbox')
  })

  it('keeps arrow, Home and End keyboard navigation', () => {
    mockReducedMotion(false)
    render(<Tabs items={items} label="Features" autoAdvanceMs={1000} />)
    const tablist = screen.getByRole('tablist', { name: 'Features' })

    fireEvent.keyDown(tablist, { key: 'ArrowLeft' })
    expect(selectedTab()).toHaveTextContent('Analytics')
    expect(selectedTab()).toHaveFocus()
    expect(screen.getByRole('tabpanel')).toHaveAttribute('data-direction', 'back')

    fireEvent.keyDown(tablist, { key: 'ArrowRight' })
    expect(selectedTab()).toHaveTextContent('Campaigns')
    expect(screen.getByRole('tabpanel')).toHaveAttribute('data-direction', 'forward')

    fireEvent.keyDown(tablist, { key: 'End' })
    expect(selectedTab()).toHaveTextContent('Analytics')
    fireEvent.keyDown(tablist, { key: 'Home' })
    expect(selectedTab()).toHaveTextContent('Campaigns')
    expect(selectedTab()).toHaveAttribute('tabindex', '0')
    expect(screen.getByRole('tabpanel')).toHaveAttribute('aria-labelledby', selectedTab().id)

    // Keyboard selection counts as picking a tab.
    act(() => {
      selectedTab().blur()
      vi.advanceTimersByTime(5000)
    })
    expect(selectedTab()).toHaveTextContent('Campaigns')
  })

  it('does not auto-advance with reduced motion', () => {
    mockReducedMotion(true)
    const { container } = render(<Tabs items={items} label="Features" autoAdvanceMs={1000} />)

    act(() => vi.advanceTimersByTime(5000))
    expect(selectedTab()).toHaveTextContent('Campaigns')
    expect(container.querySelector('.tabs-progress')).toBeNull()
  })
})
