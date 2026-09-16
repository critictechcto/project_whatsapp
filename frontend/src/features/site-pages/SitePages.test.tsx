import { render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import App from '../../App'
import { site } from '../../config/site'
import { sitePageFor } from './paths'

function visit(path: string) {
  window.history.replaceState(null, '', path)
  return render(<App />)
}

function robotsMeta() {
  return document.head.querySelector('meta[name="robots"]')
}

afterEach(() => {
  window.history.replaceState(null, '', '/')
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

  it.each(['/privacy/', '/terms/'])('%s shows the draft note and noindex until legal details are filled', async (path) => {
    const view = visit(path)
    await screen.findByRole('heading', { level: 1 })

    expect(screen.getByRole('note')).toHaveTextContent('Draft — details pending')
    expect(robotsMeta()).toHaveAttribute('content', 'noindex')

    view.unmount()
    expect(robotsMeta()).toBeNull()
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
