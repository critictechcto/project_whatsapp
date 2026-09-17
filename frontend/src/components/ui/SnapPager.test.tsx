import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { SnapPager } from './SnapPager'
import { useSnapRow } from './useSnapRow'

const names = ['Starter', 'Growth', 'Pro']

function Row({ showLabels }: { showLabels?: boolean }) {
  const { ref, index, goTo } = useSnapRow<HTMLUListElement>()
  return (
    <>
      <ul ref={ref}>
        {names.map((name) => (
          <li key={name}>{name} card</li>
        ))}
      </ul>
      <SnapPager label="Show plan" labels={names} index={index} onSelect={goTo} showLabels={showLabels} />
    </>
  )
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('SnapPager', () => {
  it('marks the current item and scrolls the row to the one picked', () => {
    const scrollTo = vi.fn()
    Object.defineProperty(HTMLElement.prototype, 'scrollTo', { configurable: true, value: scrollTo })
    render(<Row showLabels />)

    const group = screen.getByRole('group', { name: 'Show plan' })
    expect(group).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Starter' })).toHaveAttribute('aria-current', 'true')

    fireEvent.click(screen.getByRole('button', { name: 'Pro' }))
    expect(scrollTo).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('button', { name: 'Pro' })).toHaveAttribute('aria-current', 'true')
    expect(screen.getByRole('button', { name: 'Starter' })).not.toHaveAttribute('aria-current')
  })

  it('names dot buttons for screen readers', () => {
    render(<Row />)
    expect(screen.getAllByRole('button')).toHaveLength(names.length)
    expect(screen.getByRole('button', { name: 'Growth' })).toHaveTextContent('')
  })
})
