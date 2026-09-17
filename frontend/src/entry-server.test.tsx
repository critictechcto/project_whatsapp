import { act, StrictMode } from 'react'
import { hydrateRoot, type Root } from 'react-dom/client'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { render } from './entry-server'

function mockReducedMotion(reduce: boolean) {
  vi.spyOn(window, 'matchMedia').mockImplementation(
    (query: string) =>
      ({
        matches: reduce && query.includes('prefers-reduced-motion: reduce'),
        media: query,
        onchange: null,
        addListener: () => {},
        removeListener: () => {},
        addEventListener: () => {},
        removeEventListener: () => {},
        dispatchEvent: () => false,
      }) as MediaQueryList,
  )
}

// hydrateRoot is called directly (not through Testing Library), so opt in to act() here.
;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

describe('landing page prerender', () => {
  let container: HTMLDivElement | null = null
  let root: Root | null = null

  afterEach(() => {
    // Unmount so the page's timers stop before the worker tears down.
    act(() => root?.unmount())
    root = null
    container?.remove()
    container = null
  })

  it.each([false, true])('hydrates without mismatches (reduced motion: %s)', async (reduce) => {
    // The real prerender runs in Node, where no media query matches; the visitor's browser may differ.
    mockReducedMotion(false)
    const markup = await render()
    expect(markup).toContain('id="main"')
    mockReducedMotion(reduce)

    container = document.createElement('div')
    container.innerHTML = markup
    document.body.append(container)
    const heading = container.querySelector('h1')

    const errors: unknown[] = []
    const consoleError = vi.spyOn(console, 'error').mockImplementation((...args) => errors.push(args))
    await act(async () => {
      root = hydrateRoot(
        container!,
        <StrictMode>
          <App />
        </StrictMode>,
        { onRecoverableError: (error) => errors.push(error) },
      )
    })
    consoleError.mockRestore()

    expect(errors).toEqual([])
    // Hydration kept the prerendered nodes instead of rendering the page again.
    expect(container.querySelector('h1')).toBe(heading)
  })
})
