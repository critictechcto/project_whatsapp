import { render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../../App'
import { site } from '../../config/site'
import { sitePageFor } from './paths'

// The real config by default; tests flip `legalReady` or add the optional phone/GSTIN.
const legal = vi.hoisted(() => ({ ready: true, extra: {} as { phone?: string; gstin?: string } }))

vi.mock('../../config/site', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../config/site')>()
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

function visit(path: string) {
  window.history.replaceState(null, '', path)
  return render(<App />)
}

function robotsMeta() {
  return document.head.querySelector('meta[name="robots"]')
}

afterEach(() => {
  window.history.replaceState(null, '', '/')
  legal.ready = true
  legal.extra = {}
})

describe('sitePageFor', () => {
  it('matches page paths with or without a trailing slash', () => {
    expect(sitePageFor('/privacy')).toBe('privacy')
    expect(sitePageFor('/privacy/')).toBe('privacy')
    expect(sitePageFor('/terms/index.html')).toBe('terms')
    expect(sitePageFor('/contact')).toBe('contact')
    expect(sitePageFor('/')).toBeNull()
    expect(sitePageFor('/privacy/extra')).toBeNull()
    expect(sitePageFor('/app/login')).toBeNull()
  })
})

describe('site pages', () => {
  const cases = [
    ['/privacy', 'Privacy policy'],
    ['/privacy/', 'Privacy policy'],
    ['/terms', 'Terms of service'],
    ['/terms/', 'Terms of service'],
    ['/contact', 'Talk to us'],
    ['/contact/', 'Talk to us'],
  ] as const

  it.each(cases)('App routes %s to its page', async (path, heading) => {
    visit(path)
    expect(await screen.findByRole('heading', { level: 1, name: heading })).toBeInTheDocument()
  })

  it.each(['/privacy/', '/terms/'])('%s is final: operator shown, no draft note, indexable', async (path) => {
    visit(path)
    await screen.findByRole('heading', { level: 1 })

    expect(screen.getByText(site.legal.entityName)).toBeInTheDocument()
    expect(screen.queryByText(/Draft — details pending/)).not.toBeInTheDocument()
    expect(robotsMeta()).toBeNull()
  })

  it('privacy explains how to delete data received from Meta', async () => {
    visit('/privacy/')
    expect(await screen.findByRole('heading', { name: 'Deleting data received from Meta' })).toBeInTheDocument()
  })

  it('sets the document title and restores it on unmount', async () => {
    document.title = 'Landing'
    const view = visit('/privacy/')
    await screen.findByRole('heading', { level: 1 })
    expect(document.title).toBe(`Privacy policy — ${site.name}`)

    view.unmount()
    expect(document.title).toBe('Landing')
  })

  it('does not mark the contact page noindex', async () => {
    visit('/contact/')
    await screen.findByRole('heading', { level: 1 })
    expect(robotsMeta()).toBeNull()
    expect(screen.queryByRole('note')).not.toBeInTheDocument()
  })

  it('links navbar sections back to the landing page', async () => {
    visit('/terms/')
    await screen.findByRole('heading', { level: 1 })

    const primary = screen.getByRole('navigation', { name: 'Primary' })
    const faq = within(primary).getByRole('link', { name: 'FAQ' })
    expect(faq).toHaveAttribute('href', `${import.meta.env.BASE_URL}#faq`)
    expect(screen.getByRole('link', { name: `${site.name} home` })).toHaveAttribute('href', import.meta.env.BASE_URL)

    const footer = screen.getByRole('navigation', { name: 'Footer' })
    expect(within(footer).getByRole('link', { name: 'Pricing' })).toHaveAttribute(
      'href',
      `${import.meta.env.BASE_URL}#pricing`,
    )
  })

  it('shows sales and support mailto links from the site config', async () => {
    visit('/contact/')
    await screen.findByRole('heading', { level: 1 })

    const sales = screen.getByRole('region', { name: 'Sales' })
    const support = screen.getByRole('region', { name: 'Support' })
    expect(within(sales).getByRole('link', { name: site.email.sales })).toHaveAttribute(
      'href',
      `mailto:${site.email.sales}`,
    )
    expect(within(support).getByRole('link', { name: site.email.support })).toHaveAttribute(
      'href',
      `mailto:${site.email.support}`,
    )
    expect(screen.getByRole('link', { name: /WhatsApp Business Platform status/ })).toHaveAttribute(
      'href',
      'https://metastatus.com/whatsapp-business-api',
    )
  })
})

describe('contact page company card', () => {
  async function companyCard() {
    visit('/contact/')
    await screen.findByRole('heading', { level: 1 })
    return screen.getByRole('region', { name: 'Company' })
  }

  it('names the operating company and registered address', async () => {
    const card = await companyCard()
    expect(within(card).getByText(site.legal.entityName)).toBeInTheDocument()
    expect(within(card).getByText(`Registered address: ${site.legal.registeredAddress}`)).toBeInTheDocument()
    expect(card.querySelector('address')).not.toBeNull()
    expect(within(card).queryByRole('link', { name: 'Chat on WhatsApp' })).not.toBeInTheDocument()
    expect(card.querySelector('a[href^="tel:"]')).toBeNull()
    expect(within(card).queryByText(/GSTIN/)).not.toBeInTheDocument()
  })

  it('shows phone, WhatsApp and GSTIN once they are set', async () => {
    legal.extra = { phone: '+91 98765 43210', gstin: '33ABCDE1234F1Z5' }
    const card = await companyCard()
    expect(within(card).getByRole('link', { name: '+91 98765 43210' })).toHaveAttribute('href', 'tel:+919876543210')
    expect(within(card).getByRole('link', { name: 'Chat on WhatsApp' })).toHaveAttribute(
      'href',
      'https://wa.me/919876543210',
    )
    expect(within(card).getByText('GSTIN: 33ABCDE1234F1Z5')).toBeInTheDocument()
  })

  it('is hidden while legal details are pending', async () => {
    legal.ready = false
    visit('/contact/')
    await screen.findByRole('heading', { level: 1 })
    expect(screen.queryByRole('region', { name: 'Company' })).not.toBeInTheDocument()
    expect(screen.queryByText(site.legal.registeredAddress, { exact: false })).not.toBeInTheDocument()
  })
})

describe('not-found page', () => {
  it.each(['/nope', '/pricing', '/privacy/extra', '/blog/post/'])('App shows it for %s', async (path) => {
    const view = visit(path)

    expect(await screen.findByRole('heading', { level: 1, name: 'This page doesn’t exist' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Go to the home page' })).toHaveAttribute('href', '/')
    expect(screen.getByRole('link', { name: 'Contact us' })).toHaveAttribute('href', site.links.contact)
    expect(robotsMeta()).toHaveAttribute('content', 'noindex')
    expect(document.head.querySelector('link[rel="canonical"]')).toBeNull()

    view.unmount()
    expect(robotsMeta()).toBeNull()
  })

  it('does not replace the landing page', () => {
    const view = visit('/')
    expect(screen.queryByRole('heading', { level: 1, name: 'This page doesn’t exist' })).toBeNull()
    view.unmount()
  })
})

describe('canonical links', () => {
  it.each([
    ['/privacy', 'https://upchatz.com/privacy/'],
    ['/terms/', 'https://upchatz.com/terms/'],
    ['/contact', 'https://upchatz.com/contact/'],
  ])('%s points at %s and removes it on unmount', async (path, url) => {
    const view = visit(path)
    await screen.findByRole('heading', { level: 1 })

    expect(document.head.querySelector('link[rel="canonical"]')).toHaveAttribute('href', url)
    expect(document.head.querySelector('meta[property="og:url"]')).toHaveAttribute('content', url)

    view.unmount()
    expect(document.head.querySelector('link[rel="canonical"]')).toBeNull()
  })
})
