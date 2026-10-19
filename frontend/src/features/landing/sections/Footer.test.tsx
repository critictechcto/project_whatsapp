import { render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { site } from '../../../config/site'
import { Footer } from './Footer'

const legal = vi.hoisted(() => ({ ready: false, extra: {} as { phone?: string; gstin?: string } }))

vi.mock('../../../config/site', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../config/site')>()
  return {
    ...actual,
    get legalReady() {
      return legal.ready
    },
    site: {
      ...actual.site,
      get legal() {
        return { ...actual.site.legal, ...legal.extra }
      },
    },
  }
})

afterEach(() => {
  legal.ready = false
  legal.extra = {}
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

  it('names the operating company and its address once legal details are ready', () => {
    legal.ready = true
    render(<Footer />)
    expect(screen.getByText(`${site.name} is operated by ${site.legal.entityName}`)).toBeInTheDocument()
    expect(screen.getByText(site.legal.registeredAddress)).toBeInTheDocument()
    // Phone, WhatsApp and GSTIN stay hidden while unset.
    expect(screen.queryByRole('link', { name: 'Chat on WhatsApp' })).not.toBeInTheDocument()
    expect(document.querySelector('a[href^="tel:"]')).toBeNull()
    expect(screen.queryByText(/GSTIN/)).not.toBeInTheDocument()
  })

  it('hides the company identity while legal details are pending', () => {
    render(<Footer />)
    expect(screen.queryByText(site.legal.registeredAddress)).not.toBeInTheDocument()
    expect(screen.queryByText(/is operated by/)).not.toBeInTheDocument()
  })

  it('shows phone, WhatsApp and GSTIN once they are set', () => {
    legal.ready = true
    legal.extra = { phone: '+91 98765 43210', gstin: '33ABCDE1234F1Z5' }
    render(<Footer />)
    expect(screen.getByRole('link', { name: '+91 98765 43210' })).toHaveAttribute('href', 'tel:+919876543210')
    expect(screen.getByRole('link', { name: 'Chat on WhatsApp' })).toHaveAttribute(
      'href',
      'https://wa.me/919876543210',
    )
    expect(screen.getByText('GSTIN: 33ABCDE1234F1Z5')).toBeInTheDocument()
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
