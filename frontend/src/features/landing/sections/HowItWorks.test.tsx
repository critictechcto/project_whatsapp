import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { HowItWorks } from './HowItWorks'

describe('HowItWorks', () => {
  it('keeps every setup step and journey station as real text in labelled lists', () => {
    render(<HowItWorks />)

    const steps = screen.getByRole('list', { name: 'Setup steps' })
    expect(within(steps).getAllByRole('listitem')).toHaveLength(4)
    expect(within(steps).getByRole('heading', { level: 3, name: 'Connect WhatsApp with Meta' })).toBeInTheDocument()

    const journey = screen.getByRole('list', { name: 'Message journey' })
    expect(within(journey).getAllByRole('listitem')).toHaveLength(4)
    expect(within(journey).getByRole('heading', { level: 4, name: /WhatsApp Cloud API/ })).toBeInTheDocument()
  })

  it('collapses the Connect WhatsApp detail on phones behind a disclosure button', async () => {
    const user = userEvent.setup()
    render(<HowItWorks />)

    const button = screen.getByRole('button', { name: 'Show the details' })
    expect(button).toHaveAttribute('aria-expanded', 'false')
    const details = document.getElementById(button.getAttribute('aria-controls')!)!
    // Only hidden below md; the text stays in the DOM.
    expect(details).toHaveClass('max-md:hidden')
    expect(within(details).getByText('The phone number ID you selected')).toBeInTheDocument()

    await user.click(button)
    expect(button).toHaveAttribute('aria-expanded', 'true')
    expect(button).toHaveAccessibleName('Hide the details')
    expect(details).not.toHaveClass('max-md:hidden')
  })
})
