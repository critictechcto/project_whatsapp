import { act, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Navbar } from './Navbar'

type Callback = (entries: Partial<IntersectionObserverEntry>[]) => void

let observerCallback: Callback | null = null

class FakeIntersectionObserver {
  constructor(callback: Callback) {
    observerCallback = callback
  }
  observe() {}
  disconnect() {}
}

afterEach(() => {
  observerCallback = null
  document.querySelectorAll('section[data-test-section]').forEach((section) => section.remove())
  window.history.replaceState(null, '', '/')
})

describe('Navbar', () => {
  it('uses in-page anchors on the landing page', () => {
    render(<Navbar />)
    const primary = screen.getByRole('navigation', { name: 'Primary' })
    expect(within(primary).getByRole('link', { name: 'Pricing' })).toHaveAttribute('href', '#pricing')
    expect(screen.getByRole('link', { name: /home/ })).toHaveAttribute('href', '#top')
  })

  it('marks the nav item of the section on screen', () => {
    vi.stubGlobal('IntersectionObserver', FakeIntersectionObserver)
    for (const id of ['product', 'pricing']) {
      const section = document.createElement('section')
      section.id = id
      section.dataset.testSection = ''
      document.body.appendChild(section)
    }

    render(<Navbar />)
    const primary = screen.getByRole('navigation', { name: 'Primary' })
    const pricing = within(primary).getByRole('link', { name: 'Pricing' })
    expect(pricing).not.toHaveAttribute('aria-current')

    act(() => observerCallback?.([{ target: document.getElementById('pricing')!, isIntersecting: true }]))
    expect(pricing).toHaveAttribute('aria-current', 'true')
    expect(within(primary).getByRole('link', { name: 'Product' })).not.toHaveAttribute('aria-current')

    act(() => observerCallback?.([{ target: document.getElementById('pricing')!, isIntersecting: false }]))
    expect(pricing).not.toHaveAttribute('aria-current')

    vi.unstubAllGlobals()
  })
})
