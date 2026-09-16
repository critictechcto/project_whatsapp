import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Accordion } from './Accordion'

const items = [
  { question: 'Do I need a new phone number?', answer: 'No.' },
  { question: 'Can I cancel anytime?', answer: 'Yes.' },
]

describe('Accordion', () => {
  it('opens the first item and toggles aria-expanded, one item at a time', () => {
    render(<Accordion items={items} />)
    const first = screen.getByRole('button', { name: 'Do I need a new phone number?' })
    const second = screen.getByRole('button', { name: 'Can I cancel anytime?' })

    expect(first).toHaveAttribute('aria-expanded', 'true')
    expect(second).toHaveAttribute('aria-expanded', 'false')
    const secondPanel = document.getElementById(second.getAttribute('aria-controls')!)!
    expect(secondPanel).toHaveAttribute('role', 'region')
    expect(secondPanel).toHaveAttribute('aria-labelledby', second.id)
    expect(secondPanel).toHaveAttribute('data-open', 'false')
    expect(secondPanel).toHaveAttribute('inert')

    fireEvent.click(second)
    expect(second).toHaveAttribute('aria-expanded', 'true')
    expect(first).toHaveAttribute('aria-expanded', 'false')
    expect(secondPanel).toHaveAttribute('data-open', 'true')
    expect(secondPanel).not.toHaveAttribute('inert')

    fireEvent.click(second)
    expect(second).toHaveAttribute('aria-expanded', 'false')
  })
})
