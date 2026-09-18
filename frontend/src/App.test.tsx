import { render } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'

const realLocation = window.location

function stubLocation(pathname: string) {
  const replace = vi.fn()
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: { ...realLocation, pathname, replace },
  })
  return replace
}

afterEach(() => {
  Object.defineProperty(window, 'location', { configurable: true, value: realLocation })
  vi.unstubAllEnvs()
})

describe('app-only builds (app.upchatz.com)', () => {
  it.each(['/', '/privacy/', '/contact/'])('send %s to the dashboard instead of a landing page', (path) => {
    vi.stubEnv('VITE_APP_ONLY', 'true')
    const replace = stubLocation(path)

    const { container } = render(<App />)

    expect(replace).toHaveBeenCalledWith(`${import.meta.env.BASE_URL}app/`)
    expect(container).toBeEmptyDOMElement()
  })

  it('render the landing page at / in normal builds', () => {
    const replace = stubLocation('/')

    const { container } = render(<App />)

    expect(replace).not.toHaveBeenCalled()
    expect(container.querySelector('#main')).not.toBeNull()
  })
})

describe('sites with VITE_APP_URL (upchatz.com)', () => {
  it('send /app paths to the same path on the dashboard host', () => {
    vi.stubEnv('VITE_APP_URL', 'https://app.upchatz.com')
    const replace = stubLocation(`${import.meta.env.BASE_URL}app/login`)
    Object.assign(window.location, { search: '?next=1', hash: '' })

    render(<App />)

    expect(replace).toHaveBeenCalledWith('https://app.upchatz.com/app/login?next=1')
  })

  it('link log in and sign up to the dashboard host', async () => {
    vi.stubEnv('VITE_APP_URL', 'https://app.upchatz.com/')
    vi.resetModules()
    const { site } = await import('./config/site')

    expect(site.links.login).toBe('https://app.upchatz.com/app/login')
    expect(site.links.signup).toBe('https://app.upchatz.com/app/register')
  })
})
