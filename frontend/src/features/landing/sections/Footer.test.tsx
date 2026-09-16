import { render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { site } from '../../../config/site'
import { Footer } from './Footer'

const legal = vi.hoisted(() => ({ ready: false }))

vi.mock('../../../config/site', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../config/site')>()
  return {
    ...actual,
    get legalReady() {
      return legal.ready
    },
  }
})

afterEach(() => {
  legal.ready = false
})

function footerNav() {
  render(<Footer />)
  return screen.getByRole('navigation', { name: 'Footer' })
}

describe('Footer', () => {
  it('hides the legal links while legal details are pending', () => {
    const nav = footerNav()
    expect(within(nav).queryByRole('link', { name: 'Privacy policy' })).not.toBeInTheDocument()
    expect(within(nav).queryByRole('link', { name: 'Terms of service' })).not.toBeInTheDocument()
    expect(nav.querySelector('a[href="#"]')).toBeNull()
  })

  it('links the legal pages once legal details are ready', () => {
    legal.ready = true
    const nav = footerNav()
    expect(within(nav).getByRole('link', { name: 'Privacy policy' })).toHaveAttribute('href', site.links.privacy)
    expect(within(nav).getByRole('link', { name: 'Terms of service' })).toHaveAttribute('href', site.links.terms)
  })

  it('sends sales and support to the contact page and sections to in-page anchors', () => {
    const nav = footerNav()
    expect(within(nav).getByRole('link', { name: 'Contact sales' })).toHaveAttribute(
      'href',
      `${site.links.contact}#sales`,
    )
    expect(within(nav).getByRole('link', { name: 'Support' })).toHaveAttribute('href', `${site.links.contact}#support`)
    expect(within(nav).getByRole('link', { name: 'FAQ' })).toHaveAttribute('href', '#faq')
  })
})
