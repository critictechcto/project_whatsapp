import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MagneticButton } from './MagneticButton'

function mockMedia(matching: (query: string) => boolean) {
  vi.spyOn(window, 'matchMedia').mockImplementation(
    (query: string) =>
      ({
        matches: matching(query),
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

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

function wrapperOf(link: HTMLElement) {
  return link.parentElement!
}

describe('MagneticButton', () => {
  it('renders a link with its href inside the magnetic wrapper', () => {
    mockMedia(() => false)
    render(
      <MagneticButton href="/app/register" wrapperClassName="mt-7 flex" className="w-full">
        Start free trial
      </MagneticButton>,
    )

    const link = screen.getByRole('link', { name: 'Start free trial' })
    expect(link).toHaveAttribute('href', '/app/register')
    expect(link).toHaveClass('w-full')
    expect(wrapperOf(link)).toHaveClass('magnetic', 'mt-7', 'flex')
  })

  it('does nothing without a fine pointer', () => {
    vi.useFakeTimers()
    mockMedia(() => false)
    render(<MagneticButton href="#signup">Start</MagneticButton>)
    const wrapper = wrapperOf(screen.getByRole('link', { name: 'Start' }))

    fireEvent.pointerMove(wrapper, { pointerType: 'mouse', clientX: 80, clientY: 30 })
    act(() => vi.advanceTimersByTime(50))

    expect(wrapper.style.getPropertyValue('--magnetic-x')).toBe('')
    expect(wrapper).not.toHaveAttribute('data-magnetic')
  })

  it('follows a fine pointer within the limit and springs back on leave', () => {
    vi.useFakeTimers()
    mockMedia((query) => query.includes('pointer: fine'))
    render(
      <MagneticButton href="#signup" max={8}>
        Start
      </MagneticButton>,
    )
    const wrapper = wrapperOf(screen.getByRole('link', { name: 'Start' }))
    vi.spyOn(wrapper, 'getBoundingClientRect').mockReturnValue(new DOMRect(0, 0, 100, 40))

    fireEvent.pointerMove(wrapper, { pointerType: 'mouse', clientX: 100, clientY: 20 })
    act(() => vi.advanceTimersByTime(50))
    expect(wrapper).toHaveAttribute('data-magnetic', 'active')
    expect(wrapper.style.getPropertyValue('--magnetic-x')).toBe('8.0px')
    expect(wrapper.style.getPropertyValue('--magnetic-y')).toBe('0.0px')

    fireEvent.pointerLeave(wrapper)
    expect(wrapper.style.getPropertyValue('--magnetic-x')).toBe('0px')
    expect(wrapper).not.toHaveAttribute('data-magnetic')
  })
})
