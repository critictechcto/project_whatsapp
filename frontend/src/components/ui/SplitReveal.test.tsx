import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { SectionHeader } from './SectionHeader'
import { SplitReveal } from './SplitReveal'

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
  vi.restoreAllMocks()
})

describe('SplitReveal', () => {
  it('splits words for the animation but keeps one accessible name', () => {
    mockMedia(() => false)
    const { container } = render(<SplitReveal>Simple plans. Meta’s fees at cost.</SplitReveal>)

    const heading = screen.getByRole('heading', { level: 2, name: 'Simple plans. Meta’s fees at cost.' })
    expect(heading).toHaveClass('split-reveal')
    const words = container.querySelectorAll('.split-reveal-word')
    expect(Array.from(words, (word) => word.textContent)).toEqual(['Simple', 'plans.', 'Meta’s', 'fees', 'at', 'cost.'])
    expect(words[0].closest('[aria-hidden="true"]')).not.toBeNull()
    expect(screen.getByText('Simple plans. Meta’s fees at cost.')).toHaveClass('sr-only')
  })

  it('renders plain text with reduced motion', () => {
    mockMedia((query) => query.includes('prefers-reduced-motion: reduce'))
    const { container } = render(<SplitReveal>Questions we hear every week.</SplitReveal>)

    const heading = screen.getByRole('heading', { level: 2, name: 'Questions we hear every week.' })
    expect(heading.childElementCount).toBe(0)
    expect(heading).toHaveTextContent(/^Questions we hear every week\.$/)
    expect(container.querySelector('.split-reveal-word')).toBeNull()
  })

  it('gives every SectionHeader title the reveal', () => {
    mockMedia(() => false)
    render(<SectionHeader index="11" eyebrow="FAQ" title="Questions we hear every week." />)

    const heading = screen.getByRole('heading', { level: 2, name: 'Questions we hear every week.' })
    expect(heading.querySelectorAll('.split-reveal-word')).toHaveLength(5)
  })
})
