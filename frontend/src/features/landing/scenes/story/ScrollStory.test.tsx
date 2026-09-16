import { render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ScrollStory } from './ScrollStory'
import { storyChapters } from './storyChapters'

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

describe('ScrollStory', () => {
  it('renders the pinned story with every chapter as real text and the CSS stage in jsdom', async () => {
    mockReducedMotion(false)
    const getContext = vi.spyOn(HTMLCanvasElement.prototype, 'getContext')
    const { container } = render(<ScrollStory />)

    const section = container.querySelector<HTMLElement>('section#story')!
    expect(section).toHaveAttribute('data-story-mode', 'pinned')
    expect(
      within(section).getByRole('heading', { level: 2, name: 'From first message to delivered order.' }),
    ).toBeInTheDocument()

    const titles = within(section)
      .getAllByRole('heading', { level: 3 })
      .map((heading) => heading.textContent)
    expect(titles).toEqual(storyChapters.map((chapter) => chapter.title))
    expect(titles).toHaveLength(5)

    expect(screen.getByText(/own Razorpay or Cashfree account/)).toBeInTheDocument()
    expect(screen.getByText(/never holds it/)).toBeInTheDocument()
    expect(screen.getByText('An approved template reaches opted-in buyers').closest('li')).toHaveAttribute(
      'data-state',
      'current',
    )

    // jsdom has no WebGL: the decorative CSS stage loads and no canvas is created.
    const stage = await vi.waitFor(() => {
      const element = container.querySelector('.sf-stage')
      if (!element) throw new Error('stage not loaded')
      return element
    })
    expect(stage).toHaveAttribute('aria-hidden', 'true')
    expect(container.querySelector('canvas')).toBeNull()
    expect(getContext).not.toHaveBeenCalledWith('webgl2')
  })

  it('lists every chapter statically with reduced motion', async () => {
    mockReducedMotion(true)
    const { container } = render(<ScrollStory />)

    const section = container.querySelector<HTMLElement>('section#story')!
    expect(section).toHaveAttribute('data-story-mode', 'static')
    expect(section.querySelector('.sticky')).toBeNull()
    expect(section.querySelector('[class*="400vh"]')).toBeNull()

    const items = within(section).getAllByRole('listitem')
    expect(items).toHaveLength(5)
    storyChapters.forEach((chapter, i) => {
      expect(within(items[i]).getByRole('heading', { level: 3, name: chapter.title })).toBeInTheDocument()
      expect(within(items[i]).getByText(chapter.body)).toBeInTheDocument()
    })

    // The flat illustrations load without any scroll-scrubbed styles.
    expect(await within(items[4]).findAllByText('Mark shipped')).not.toHaveLength(0)
    expect(section.querySelector('.sf-stage, .sf-msg, .sf-prop')).toBeNull()
  })
})
