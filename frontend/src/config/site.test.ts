import { afterEach, describe, expect, it } from 'vitest'
import { isLandingPath, legalReady, sectionHref, site } from './site'

// Tests run with the default deploy base, `/`.

afterEach(() => {
  window.history.replaceState(null, '', '/')
})

describe('sectionHref', () => {
  it('is an in-page anchor on the landing page', () => {
    expect(sectionHref('faq', '/')).toBe('#faq')
    expect(sectionHref('faq', '/index.html')).toBe('#faq')
  })

  it('points back to the landing page from other pages', () => {
    expect(sectionHref('faq', '/privacy/')).toBe('/#faq')
    expect(sectionHref('pricing', '/contact')).toBe('/#pricing')
  })

  it('reads the current location by default', () => {
    window.history.replaceState(null, '', '/terms/')
    expect(isLandingPath()).toBe(false)
    expect(sectionHref('product')).toBe('/#product')

    window.history.replaceState(null, '', '/')
    expect(isLandingPath()).toBe(true)
    expect(sectionHref('product')).toBe('#product')
  })
})

describe('site config', () => {
  it('builds page links from the deploy base', () => {
    expect(site.links.privacy).toBe('/privacy/')
    expect(site.links.terms).toBe('/terms/')
    expect(site.links.contact).toBe('/contact/')
  })

  it('is not legally ready while legal details are empty', () => {
    expect(site.legal.entityName).toBe('')
    expect(legalReady).toBe(false)
  })
})
