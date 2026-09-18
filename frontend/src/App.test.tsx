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
