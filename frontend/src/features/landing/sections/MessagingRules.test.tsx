import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { MessagingRules } from './MessagingRules'

describe('Messaging rules section', () => {
  it('shows the rules as disclosures on phones with the first one open', async () => {
    const user = userEvent.setup()
    render(<MessagingRules />)

    const rule1 = screen.getByRole('button', { name: /Rule 1\s*The 24-hour customer service window/ })
    const rule3 = screen.getByRole('button', { name: /Rule 3\s*Customers must opt in/ })
    expect(rule1).toHaveAttribute('aria-expanded', 'true')
    expect(rule3).toHaveAttribute('aria-expanded', 'false')

    // Closed bodies are hidden below md only; every id the button controls exists.
    const controlled = rule3.getAttribute('aria-controls')!.split(' ')
    const body = document.getElementById(controlled[0])!
    expect(body).toHaveClass('max-md:hidden')
    expect(body).toHaveTextContent(/Bought or scraped lists are not allowed/)

    await user.click(rule3)
    expect(rule3).toHaveAttribute('aria-expanded', 'true')
    expect(body).not.toHaveClass('max-md:hidden')

    await user.click(rule1)
    expect(rule1).toHaveAttribute('aria-expanded', 'false')
    for (const id of rule1.getAttribute('aria-controls')!.split(' ')) {
      expect(document.getElementById(id)).toHaveClass('max-md:hidden')
    }
  })

  it('keeps the hedged pricing copy', () => {
    render(<MessagingRules />)
    expect(screen.getByText('Free under Meta’s current pricing')).toBeInTheDocument()
    expect(screen.getByRole('group', { name: 'Message categories' })).toBeInTheDocument()
  })
})
